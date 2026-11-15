# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for config env."""

import importlib

import pytest

from bot.config.env import get_bool, get_optional_int
from bot.config.model import (
    ConfigError,
    get_settings,
    load_settings,
    reset_settings_cache,
)


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


def test_load_env_file_loads_env_from_project_root_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load env file uses the project root path."""
    config_module = importlib.import_module("bot.config")
    env_module = importlib.import_module("bot.config.env")
    project_root = importlib.import_module("bot.config.paths").PROJECT_ROOT

    loaded_paths = []
    monkeypatch.setattr(
        env_module,
        "load_dotenv",
        loaded_paths.append,
    )

    config_module.load_env_file()

    assert loaded_paths == [project_root / ".env"]


def test_load_settings_uses_the_supplied_environment() -> None:
    """Load settings reads values from the supplied mapping."""
    settings = load_settings(
        {
            "BOT_TOKEN": " test-token ",
            "SUPERVISOR_ID": "42",
            "ADMIN_IDS": "10, 20",
            "ALLOWED_USERS": "30",
            "ALLOW_ALL_USERS": "yes",
            "LLM_BASE_URL": "http://llm.test/v1///",
            "LLM_TEMPERATURE": "0.2",
            "LLM_TOP_P": "1",
            "LLM_CONTEXT_SIZE": "8192",
            "LLM_TOKEN_COUNTING": "ESTIMATE",
            "DATABASE_PATH": " data/custom.db ",
            "WHISPER_API_URL": "https://audio.test///",
            "WHISPER_API_KEY": " whisper-key ",
            "DOCUMENT_API_URL": " https://docs.test///",
            "DOCUMENT_API_KEY": " document-key ",
        }
    )

    expected_value = "test-token"
    assert expected_value == settings.BOT_TOKEN
    assert settings.SUPERVISOR_ID == 42
    assert {10, 20} == settings.ADMIN_IDS
    assert {30} == settings.ALLOWED_USERS
    assert settings.ALLOW_ALL_USERS is True
    assert settings.LLM_BASE_URL == "http://llm.test/v1"
    assert settings.LLM_TEMPERATURE == 0.2
    assert settings.LLM_TOP_P == 1.0
    assert settings.LLM_CONTEXT_SIZE == 8192
    expected_mode = "estimate"
    assert expected_mode == settings.LLM_TOKEN_COUNTING
    assert settings.DATABASE_PATH == "data/custom.db"
    assert settings.WHISPER_API_URL == "https://audio.test"
    assert settings.WHISPER_API_KEY == "whisper-key"
    assert settings.DOCUMENT_API_URL == "https://docs.test"
    assert settings.DOCUMENT_API_KEY == "document-key"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("SUPERVISOR_ID", "invalid"),
        ("ADMIN_IDS", "invalid"),
        ("ALLOWED_USERS", "0"),
        ("ALLOW_ALL_USERS", "maybe"),
        ("LLM_TEMPERATURE", "-0.1"),
        ("LLM_TOP_P", "1.1"),
        ("LLM_MAX_TOKENS", "invalid"),
        ("LLM_TIMEOUT", "0"),
        ("LLM_CONTEXT_SIZE", "invalid"),
        ("LLM_TOKEN_COUNTING", "invalid"),
        ("LLM_MAX_CONCURRENT_GENERATIONS", "0"),
        ("MAX_HISTORY_EXCHANGES", "invalid"),
        ("MAX_STORED_EXCHANGES", "0"),
        ("DATABASE_PATH", "   "),
        ("WHISPER_TIMEOUT", "invalid"),
        ("DOCUMENT_TIMEOUT", "invalid"),
    ],
)
def test_load_settings_rejects_each_invalid_setting(name: str, value: str) -> None:
    """Load settings reports an invalid environment value."""
    with pytest.raises(ConfigError) as error:
        load_settings({"SUPERVISOR_ID": "1", name: value})

    assert any(name in message for message in error.value.errors)


def test_load_settings_collects_multiple_errors() -> None:
    """Load settings reports all invalid values in one exception."""
    environ = {
        "SUPERVISOR_ID": "invalid",
        "ADMIN_IDS": "bad-id",
        "ALLOWED_USERS": "-1",
        "ALLOW_ALL_USERS": "maybe",
        "LLM_TEMPERATURE": "nan",
        "LLM_TOP_P": "2",
        "LLM_TOKEN_COUNTING": "unknown",
        "DATABASE_PATH": " ",
    }

    with pytest.raises(ConfigError) as error:
        load_settings(environ)

    assert len(error.value.errors) == len(environ)
    for name in environ:
        assert name in str(error.value)


def test_get_settings_is_cached_until_reset() -> None:
    """Get settings returns a cached instance until the cache is reset."""
    reset_settings_cache()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("SUPERVISOR_ID", "123")
            first = get_settings()
            patch.setenv("SUPERVISOR_ID", "456")

            assert get_settings() is first
            assert get_settings().SUPERVISOR_ID == 123

            reset_settings_cache()
            assert get_settings().SUPERVISOR_ID == 456
    finally:
        reset_settings_cache()


def test_legacy_config_proxy_and_config_alias_are_removed() -> None:
    """The legacy proxy and Config alias are no longer exported."""
    config_module = importlib.import_module("bot.config")
    settings_module = importlib.import_module("bot.config.settings")
    model_module = importlib.import_module("bot.config.model")

    assert not hasattr(config_module, "config")
    assert not hasattr(config_module, "Config")
    assert not hasattr(settings_module, "config")
    assert not hasattr(settings_module, "Config")
    assert not hasattr(model_module, "config")


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
    assert get_optional_int("TEST_OPTIONAL_INT") == 32768


@pytest.mark.parametrize("value", ["zero", "0", "-1"])
def test_get_optional_int_rejects_invalid_values(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Get optional int rejects invalid values."""
    monkeypatch.setenv("TEST_OPTIONAL_INT", value)
    with pytest.raises(ValueError, match="TEST_OPTIONAL_INT"):
        get_optional_int("TEST_OPTIONAL_INT")


def test_stream_update_interval_is_not_an_environment_setting() -> None:
    """Stream update interval is not an application setting."""
    settings_class = importlib.import_module("bot.config.settings").Settings

    assert not hasattr(settings_class, "STREAM_UPDATE_INTERVAL")
