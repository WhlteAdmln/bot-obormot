# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for systemd unit rendering and installation."""

from pathlib import Path

import pytest

from bot_obormot import service

UNITS = Path(__file__).resolve().parents[1] / "fixtures" / "units"


def _golden(name: str) -> str:
    return (UNITS / name).read_text(encoding="utf-8")


def _render_refusal(home: Path, mode: str = "user") -> str:
    try:
        service.render_service_unit(home, mode=mode)  # type: ignore[arg-type]  # invalid mode
    except ValueError as error:
        return str(error)
    return ""


def _install_refusal(unit_directory: Path) -> str:
    try:
        service.install_service_unit(
            Path("/srv/bot-obormot"), mode="user", unit_directory=unit_directory
        )
    except FileExistsError as error:
        return str(error)
    return ""


@pytest.mark.parametrize(
    ("home", "mode", "golden"),
    [
        ("/home/alice/bot-obormot", "user", "user.service"),
        ("/srv/bot-obormot", "system", "system.service"),
        ("/home/a b/100%/bot-obormot", "user", "user_spaces_percent.service"),
    ],
    ids=["user", "system", "spaces-and-percent"],
)
def test_render_matches_the_golden_unit(
    home: str, mode: service.ServiceMode, golden: str
) -> None:
    unit = service.render_service_unit(Path(home), mode=mode)
    assert unit == _golden(golden), "the unit differs from the golden file"


@pytest.mark.parametrize(
    "home",
    [Path("relative"), Path("bot-obormot/.."), Path("~/bot-obormot")],
    ids=["relative", "dot-dot", "tilde"],
)
def test_render_rejects_a_relative_home(home: Path) -> None:
    expected = "The bot-obormot home directory must be an absolute path."
    assert _render_refusal(home) == expected, "a relative home must be refused"


@pytest.mark.parametrize(
    "mode", ["global", "", "USER"], ids=["global", "empty", "upper"]
)
def test_render_rejects_an_unknown_mode(mode: str) -> None:
    assert _render_refusal(Path("/srv/app"), mode) == (
        f"Unsupported systemd service mode: {mode}"
    ), "an unknown mode must be refused"


@pytest.mark.parametrize(
    "home",
    ["/srv/app\nExecStart=evil", "/srv/app\rUser=root", "/srv/app\0"],
    ids=["line-feed", "carriage-return", "nul"],
)
def test_render_rejects_control_characters_in_the_home(home: str) -> None:
    expected = "must not contain null bytes or line breaks"
    assert expected in _render_refusal(Path(home)), (
        "a directive injection must be refused"
    )


def test_install_writes_the_rendered_unit(tmp_path: Path) -> None:
    unit_path = service.install_service_unit(
        Path("/srv/bot-obormot"), mode="user", unit_directory=tmp_path / "units"
    )
    expected = _golden("user.service").replace(
        "/home/alice/bot-obormot", "/srv/bot-obormot"
    )
    assert unit_path.read_text(encoding="utf-8") == expected, "wrong unit content"


def test_install_writes_the_unit_with_mode_644(tmp_path: Path) -> None:
    unit_path = service.install_service_unit(
        Path("/opt/obormot"), mode="system", unit_directory=tmp_path
    )
    expected = 0o644
    assert unit_path.stat().st_mode & 0o777 == expected, "the unit must have mode 644"


def test_install_leaves_only_the_unit_in_its_directory(tmp_path: Path) -> None:
    unit_path = service.install_service_unit(
        Path("/srv/bot-obormot"), mode="user", unit_directory=tmp_path / "units"
    )
    expected = [tmp_path / "units" / service.UNIT_NAME]
    assert list(unit_path.parent.iterdir()) == expected, "no temporary file may stay"


def test_install_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    (tmp_path / service.UNIT_NAME).write_text("old", encoding="utf-8")
    force_hint = "pass --force to replace it"
    assert force_hint in _install_refusal(tmp_path), (
        "an existing unit must be refused without force"
    )


def test_install_without_force_keeps_the_existing_unit(tmp_path: Path) -> None:
    unit_path = tmp_path / service.UNIT_NAME
    unit_path.write_text("[Service]\nExecStart=/usr/bin/custom\n", encoding="utf-8")
    _install_refusal(tmp_path)
    expected = "[Service]\nExecStart=/usr/bin/custom\n"
    assert unit_path.read_text(encoding="utf-8") == expected, "the old unit changed"


def test_install_refuses_a_dangling_symlink_without_force(tmp_path: Path) -> None:
    (tmp_path / service.UNIT_NAME).symlink_to(tmp_path / "missing.service")
    force_hint = "pass --force to replace it"
    assert force_hint in _install_refusal(tmp_path), (
        "a dangling symlink counts as an existing unit"
    )


def test_install_with_force_saves_a_backup(tmp_path: Path) -> None:
    (tmp_path / service.UNIT_NAME).write_text("old", encoding="utf-8")
    service.install_service_unit(
        Path("/srv/bot-obormot"), mode="user", force=True, unit_directory=tmp_path
    )
    backup = tmp_path / f"{service.UNIT_NAME}.bak"
    expected = "old"
    assert backup.read_text(encoding="utf-8") == expected, "the backup is wrong"


def test_install_with_force_replaces_the_unit(tmp_path: Path) -> None:
    unit_path = tmp_path / service.UNIT_NAME
    unit_path.write_text("old", encoding="utf-8")
    service.install_service_unit(
        Path("/srv/bot-obormot"), mode="user", force=True, unit_directory=tmp_path
    )
    exec_start_key = "ExecStart="
    assert exec_start_key in unit_path.read_text(encoding="utf-8"), (
        "force must write the new unit"
    )


def test_uninstall_reports_a_missing_unit(tmp_path: Path) -> None:
    removed = service.uninstall_service_unit(mode="user", unit_directory=tmp_path)
    assert removed is None, "nothing to remove must give None"


def test_uninstall_removes_only_the_unit_file(tmp_path: Path) -> None:
    (tmp_path / service.UNIT_NAME).write_text("unit", encoding="utf-8")
    neighbour = tmp_path / "other.service"
    neighbour.write_text("keep", encoding="utf-8")
    service.uninstall_service_unit(mode="user", unit_directory=tmp_path)
    expected = [neighbour]
    assert list(tmp_path.iterdir()) == expected, "only the unit file may be removed"


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("user", Path("/home/alice/.config/systemd/user")),
        ("system", Path("/etc/systemd/system")),
    ],
    ids=["user", "system"],
)
def test_default_unit_directory_depends_on_mode(
    monkeypatch: pytest.MonkeyPatch, mode: service.ServiceMode, expected: Path
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: Path("/home/alice")))
    actual = service.default_unit_directory(mode)
    assert actual == expected, "the unit directory is wrong"
