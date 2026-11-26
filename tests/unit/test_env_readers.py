# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for env readers."""

import importlib
import importlib.util
import re
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
    name = "TEST_BOOL_SETTING"
    monkeypatch.setenv(name, value)

    assert get_bool(name) is expected, f"{value!r} is parsed wrongly"


def test_get_bool_is_false_for_a_missing_value_without_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "TEST_BOOL_SETTING"
    monkeypatch.delenv(name, raising=False)

    assert get_bool(name) is False, "a missing value is not false by default"


def test_get_bool_uses_the_default_for_a_missing_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "TEST_BOOL_SETTING"
    monkeypatch.delenv(name, raising=False)

    assert get_bool(name, default=True) is True, "the default is ignored"


def test_get_bool_uses_the_default_for_a_blank_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "TEST_BOOL_SETTING"
    monkeypatch.setenv(name, "   ")

    assert get_bool(name, default=True) is True, "a blank value ignores the default"


def test_get_bool_rejects_invalid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    name = "TEST_BOOL_SETTING"
    monkeypatch.setenv(name, "sometimes")

    with pytest.raises(ValueError, match=re.escape(name)) as excinfo:
        get_bool(name)

    assert name in str(excinfo.value), "the error does not name the setting"


def test_load_env_file_uses_home_and_working_directory_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    expected_paths = [home / ".env", cwd / ".env"]
    assert loaded_paths == expected_paths, "the loaded env files differ"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_get_optional_int_returns_none_for_empty_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    name = "TEST_OPTIONAL_INT"
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)

    assert get_optional_int(name) is None, f"{value!r} is not read as missing"


def test_get_optional_int_parses_positive_integer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "TEST_OPTIONAL_INT"
    monkeypatch.setenv(name, "32768")
    expected_get_optional_int = 32768
    assert get_optional_int(name) == expected_get_optional_int, (
        "a positive integer is parsed wrongly"
    )


@pytest.mark.parametrize("value", ["zero", "0", "-1"])
def test_get_optional_int_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    name = "TEST_OPTIONAL_INT"
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=re.escape(name)) as excinfo:
        get_optional_int(name)

    assert name in str(excinfo.value), f"the error for {value!r} lacks the name"


def test_get_home_dir_resolves_a_relative_home_against_the_working_directory(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: tmp_path))
    user_home = tmp_path / "user"
    environ = {"BOT_OBORMOT_HOME": "custom", "HOME": str(user_home)}

    home_dir = env_readers.get_home_dir(environ)

    expected_home = tmp_path / "custom"
    assert home_dir == expected_home, "a relative home is resolved wrongly"


def test_get_home_dir_defaults_to_a_folder_in_the_user_home(tmp_path: Path) -> None:
    user_home = tmp_path / "someone"

    home_dir = env_readers.get_home_dir({"HOME": str(user_home)})

    expected_home = user_home / "bot-obormot"
    assert home_dir == expected_home, "the default home is not in the user home"


def test_resolve_home_path_joins_a_relative_path_to_the_home(tmp_path: Path) -> None:
    home = tmp_path / "bot-home"
    relative_path = "data/file.db"

    resolved = env_readers.resolve_home_path(relative_path, home)

    expected_path = home / relative_path
    assert resolved == expected_path, "a relative path is not joined to the home"


def test_load_env_file_skips_duplicate_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
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

    expected_calls = [(home / ".env", False), (cwd / ".env", False)]
    assert calls == expected_calls, "a duplicate env file was loaded twice"


def test_get_bool_reads_a_value_from_the_given_environ() -> None:
    environ = {"FLAG": "yes"}

    assert env_readers.get_bool("FLAG", environ=environ) is True, "yes is not true"


def test_get_bool_uses_the_default_for_an_empty_environ() -> None:
    environ: dict[str, str] = {}

    value = env_readers.get_bool("FEATURE", default=True, environ=environ)

    assert value is True, "the default is ignored for an empty environ"


def test_get_int_uses_the_fallback_text_for_a_missing_value() -> None:
    environ: dict[str, str] = {}
    expected_get_int = 3

    value = env_readers.get_int("COUNT", "3", 2, environ=environ)

    assert value == expected_get_int, "the fallback text is not parsed"


def test_get_optional_int_reads_an_empty_environ_value_as_none() -> None:
    environ = {"LIMIT": ""}

    assert env_readers.get_optional_int("LIMIT", environ=environ) is None, (
        "an empty value is not read as missing"
    )


def test_parse_ids_reads_a_comma_separated_list_without_duplicates() -> None:
    environ = {"IDS": "1, 2,2"}
    expected_ids = {1, 2}

    ids = env_readers.parse_ids("IDS", environ=environ)

    assert ids == expected_ids, "the identifiers are parsed wrongly"


def test_get_bool_rejects_a_value_that_is_not_a_boolean() -> None:
    environ = {"FLAG": "maybe"}
    expected_text = "true or false"

    with pytest.raises(ValueError, match=re.escape(expected_text)) as excinfo:
        env_readers.get_bool("FLAG", environ=environ)

    assert expected_text in str(excinfo.value), "the error does not list the choices"


def test_get_int_rejects_a_value_below_the_minimum() -> None:
    environ: dict[str, str] = {}
    expected_text = "at least 2"

    with pytest.raises(ValueError, match=re.escape(expected_text)) as excinfo:
        env_readers.get_int("COUNT", "1", 2, environ=environ)

    assert expected_text in str(excinfo.value), "the error does not name the minimum"


def test_parse_ids_rejects_a_non_positive_identifier() -> None:
    environ = {"IDS": "0"}
    expected_text = "must be positive"

    with pytest.raises(ValueError, match=re.escape(expected_text)) as excinfo:
        env_readers.parse_ids("IDS", environ=environ)

    assert expected_text in str(excinfo.value), "a zero identifier is accepted"


def test_get_float_reads_a_value_within_the_bounds() -> None:
    environ: dict[str, str] = {}
    expected_get_float = 0.5

    value = env_readers.get_float("RATE", "0.5", 0.0, 1.0, environ=environ)

    assert value == expected_get_float, "a value within the bounds is parsed wrongly"


def test_get_float_rejects_a_value_that_is_not_finite() -> None:
    environ: dict[str, str] = {}
    expected_text = "finite number"

    with pytest.raises(ValueError, match=re.escape(expected_text)) as excinfo:
        env_readers.get_float("RATE", "nan", environ=environ)

    assert expected_text in str(excinfo.value), "NaN is accepted"


def test_get_float_rejects_a_value_above_the_maximum() -> None:
    environ: dict[str, str] = {}
    expected_text = "at most 1.0"

    with pytest.raises(ValueError, match=re.escape(expected_text)) as excinfo:
        env_readers.get_float("RATE", "1.5", maximum=1.0, environ=environ)

    assert expected_text in str(excinfo.value), "the error does not name the maximum"


def test_log_level_reader_warns_and_falls_back_to_info() -> None:
    expected_get_log_level = "INFO"
    environ = {"LOG_LEVEL": "verbose"}
    with pytest.warns(RuntimeWarning, match="Falling back to INFO"):
        level = env_readers.get_log_level(environ=environ)

    assert level == expected_get_log_level, "an unknown level does not fall back"
