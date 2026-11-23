# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for env readers."""

import importlib
import importlib.util
from pathlib import Path

import pytest

from bot_obormot import env_readers
from bot_obormot.env_readers import get_bool, get_optional_int


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        (" YES ", True),
        ("on", True),
        ("0", False),
        ("false", False),
        (" NO ", False),
        ("off", False),
    ],
)
def test_get_bool_parses_supported_values(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: object
) -> None:
    """Get bool parses supported values."""
    monkeypatch.setenv("TEST_BOOL_SETTING", value)

    assert get_bool("TEST_BOOL_SETTING") is expected


def test_get_bool_uses_default_for_missing_or_empty_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Get bool uses default for missing or empty value."""
    monkeypatch.delenv("TEST_BOOL_SETTING", raising=False)
    assert get_bool("TEST_BOOL_SETTING") is False
    assert get_bool("TEST_BOOL_SETTING", default=True) is True

    monkeypatch.setenv("TEST_BOOL_SETTING", "   ")
    assert get_bool("TEST_BOOL_SETTING", default=True) is True


def test_get_bool_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """Get bool rejects invalid value."""
    monkeypatch.setenv("TEST_BOOL_SETTING", "sometimes")

    with pytest.raises(ValueError, match="TEST_BOOL_SETTING"):
        get_bool("TEST_BOOL_SETTING")


def test_load_env_file_uses_home_and_working_directory_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Load env file reads the application home first, then the current directory."""
    config_module = importlib.import_module("bot_obormot.config")
    env_module = importlib.import_module("bot_obormot.env_readers")
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    monkeypatch.setenv("BOT_OBORMOT_HOME", str(home))
    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: cwd))

    loaded_paths: list[Path] = []
    monkeypatch.setattr(
        env_module,
        "load_dotenv",
        lambda path, **_kwargs: loaded_paths.append(Path(path)),
    )

    config_module.load_env_file()

    assert loaded_paths == [home / ".env", cwd / ".env"]


@pytest.mark.parametrize("value", [None, "", "   "])
def test_get_optional_int_returns_none_for_empty_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    """Get optional int returns none for empty value."""
    if value is None:
        monkeypatch.delenv("TEST_OPTIONAL_INT", raising=False)
    else:
        monkeypatch.setenv("TEST_OPTIONAL_INT", value)

    assert get_optional_int("TEST_OPTIONAL_INT") is None


def test_get_optional_int_parses_positive_integer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Get optional int parses positive integer."""
    monkeypatch.setenv("TEST_OPTIONAL_INT", "32768")
    expected_get_optional_int = 32768
    assert get_optional_int("TEST_OPTIONAL_INT") == expected_get_optional_int


@pytest.mark.parametrize("value", ["zero", "0", "-1"])
def test_get_optional_int_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Get optional int rejects invalid values."""
    monkeypatch.setenv("TEST_OPTIONAL_INT", value)
    with pytest.raises(ValueError, match="TEST_OPTIONAL_INT"):
        get_optional_int("TEST_OPTIONAL_INT")


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
    expected_get_int = 3
    assert env_readers.get_int("COUNT", "3", 2, environ={}) == expected_get_int
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
    expected_get_float = 0.5
    assert (
        env_readers.get_float("RATE", "0.5", 0.0, 1.0, environ={}) == expected_get_float
    )

    with pytest.raises(ValueError, match="finite number"):
        env_readers.get_float("RATE", "nan", environ={})
    with pytest.raises(ValueError, match=r"at most 1\.0"):
        env_readers.get_float("RATE", "1.5", maximum=1.0, environ={})


def test_log_level_reader_warns_and_falls_back_to_info() -> None:
    """Invalid log levels warn and use INFO."""
    expected_get_log_level = "INFO"
    with pytest.warns(RuntimeWarning, match="Falling back to INFO"):
        assert (
            env_readers.get_log_level(environ={"LOG_LEVEL": "verbose"})
            == expected_get_log_level
        )
