# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the vendored environment readers."""

from pathlib import Path

import pytest

from bot_obormot import env_readers


def test_home_directory_and_relative_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Home settings take precedence and relative paths use the home directory."""
    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: tmp_path))
    user_home = tmp_path / "user"

    assert (
        env_readers.get_home_dir({"BOT_OBORMOT_HOME": "custom", "HOME": str(user_home)})
        == tmp_path / "custom"
    )
    assert env_readers.get_home_dir({"HOME": str(user_home)}) == (
        user_home / "bot-obormot"
    )
    assert env_readers.resolve_home_path("data/file.db", user_home) == (
        user_home / "data/file.db"
    )


def test_load_env_file_skips_duplicate_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An explicitly loaded home file is not loaded a second time."""
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    calls: list[tuple[Path, bool]] = []
    monkeypatch.setattr(env_readers, "get_home_dir", lambda: home)
    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: cwd))
    monkeypatch.setattr(
        env_readers,
        "load_dotenv",
        lambda path, override=False: calls.append((Path(path), override)),
    )

    env_readers.load_env_file(home / ".env")

    assert calls == [(home / ".env", False), (cwd / ".env", False)]


def test_boolean_integer_and_id_readers() -> None:
    """Boolean, integer and ID readers validate their inputs."""
    assert env_readers.get_bool("FLAG", environ={"FLAG": "yes"}) is True
    assert env_readers.get_bool("FLAG", default=True, environ={}) is True
    assert env_readers.get_bool("FLAG", True, environ={}) is True
    assert env_readers.get_int("COUNT", "3", 2, environ={}) == 3
    assert env_readers.get_optional_int("COUNT", environ={"COUNT": ""}) is None
    assert env_readers.parse_ids("IDS", environ={"IDS": "1, 2,2"}) == {1, 2}

    with pytest.raises(ValueError, match="true or false"):
        env_readers.get_bool("FLAG", environ={"FLAG": "maybe"})
    with pytest.raises(ValueError, match="at least 2"):
        env_readers.get_int("COUNT", "1", 2, environ={})
    with pytest.raises(ValueError, match="must be positive"):
        env_readers.parse_ids("IDS", environ={"IDS": "0"})


def test_float_reader_checks_finite_values_and_bounds() -> None:
    """Float settings must be finite and remain within configured bounds."""
    assert env_readers.get_float("RATE", "0.5", 0.0, 1.0, environ={}) == 0.5

    with pytest.raises(ValueError, match="finite number"):
        env_readers.get_float("RATE", "nan", environ={})
    with pytest.raises(ValueError, match=r"at most 1\.0"):
        env_readers.get_float("RATE", "1.5", maximum=1.0, environ={})


def test_log_level_reader_warns_and_falls_back_to_info() -> None:
    """Invalid log levels warn and use INFO."""
    with pytest.warns(RuntimeWarning, match="Falling back to INFO"):
        assert env_readers.get_log_level(environ={"LOG_LEVEL": "verbose"}) == "INFO"
