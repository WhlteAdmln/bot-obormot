# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for systemd unit rendering and installation."""

from pathlib import Path

import pytest

from bot_obormot import service

UNITS = Path(__file__).resolve().parents[1] / "fixtures" / "units"


def _golden(name: str) -> str:
    """Read one golden unit file."""
    return (UNITS / name).read_text(encoding="utf-8")


def test_user_unit_matches_golden_file() -> None:
    """The user unit runs the venv executable from the home directory."""
    unit = service.render_service_unit(Path("/home/alice/bot-obormot"), mode="user")

    assert unit == _golden("user.service")


def test_system_unit_matches_golden_file() -> None:
    """The system unit adds a service account and a filesystem sandbox."""
    unit = service.render_service_unit(Path("/srv/bot-obormot"), mode="system")

    assert unit == _golden("system.service")


def test_unit_escapes_spaces_and_percent_signs() -> None:
    """Paths with spaces and ``%`` are escaped for systemd."""
    unit = service.render_service_unit(Path("/home/a b/100%/bot-obormot"), mode="user")

    assert unit == _golden("user_spaces_percent.service")


def test_render_rejects_relative_home_and_unknown_mode() -> None:
    """Invalid input is rejected before anything is rendered."""
    with pytest.raises(ValueError, match="absolute"):
        service.render_service_unit(Path("relative"), mode="user")
    with pytest.raises(ValueError, match="Unsupported"):
        # The invalid mode is the point of this check.
        service.render_service_unit(Path("/srv/app"), mode="global")  # type: ignore[arg-type]


def test_render_rejects_line_breaks_in_paths() -> None:
    """A newline in the home path cannot inject systemd directives."""
    with pytest.raises(ValueError, match="line breaks"):
        service.render_service_unit(Path("/srv/app\nExecStart=evil"), mode="user")


def test_install_writes_a_new_unit_without_touching_systemd(tmp_path: Path) -> None:
    """A new unit is written with mode 644 and nothing else happens."""
    unit_path = service.install_service_unit(
        Path("/srv/bot-obormot"), mode="user", unit_directory=tmp_path / "units"
    )

    assert unit_path == tmp_path / "units" / service.UNIT_NAME
    assert unit_path.read_text(encoding="utf-8") == _golden("user.service").replace(
        "/home/alice/bot-obormot", "/srv/bot-obormot"
    )
    expected_number = 0o644
    assert unit_path.stat().st_mode & 0o777 == expected_number
    assert list(unit_path.parent.iterdir()) == [unit_path]


def test_install_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    """An existing unit is left untouched unless ``force`` is given."""
    unit_path = tmp_path / service.UNIT_NAME
    unit_path.write_text("old", encoding="utf-8")

    with pytest.raises(FileExistsError, match="--force"):
        service.install_service_unit(
            Path("/srv/bot-obormot"), mode="user", unit_directory=tmp_path
        )

    expected_text = "old"
    assert unit_path.read_text(encoding="utf-8") == expected_text


def test_install_with_force_saves_a_backup(tmp_path: Path) -> None:
    """Forcing a replacement keeps the previous file as ``.bak``."""
    unit_path = tmp_path / service.UNIT_NAME
    unit_path.write_text("old", encoding="utf-8")

    service.install_service_unit(
        Path("/srv/bot-obormot"), mode="user", force=True, unit_directory=tmp_path
    )

    expected_text = "old"
    assert (tmp_path / f"{service.UNIT_NAME}.bak").read_text(
        encoding="utf-8"
    ) == expected_text
    expected_fragment = "ExecStart="
    assert expected_fragment in unit_path.read_text(encoding="utf-8")


def test_uninstall_removes_only_the_unit_file(tmp_path: Path) -> None:
    """Uninstall deletes the unit and reports when none exists."""
    assert service.uninstall_service_unit(mode="user", unit_directory=tmp_path) is None

    unit_path = tmp_path / service.UNIT_NAME
    unit_path.write_text("unit", encoding="utf-8")

    assert (
        service.uninstall_service_unit(mode="user", unit_directory=tmp_path)
        == unit_path
    )
    assert not unit_path.exists()


def test_default_unit_directories(monkeypatch: pytest.MonkeyPatch) -> None:
    """User units live under ``~/.config/systemd/user``; system units in /etc."""
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: Path("/home/alice")))

    assert service.default_unit_directory("user") == Path(
        "/home/alice/.config/systemd/user"
    )
    assert service.default_unit_directory("system") == Path("/etc/systemd/system")
