# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for config model."""

from pathlib import Path

import pytest

from bot_obormot.config import load_default_system_prompt
from bot_obormot.config.model import (
    ConfigError,
    get_settings,
    load_settings,
    reset_settings_cache,
)


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
            "BOT_OBORMOT_HOME": "/srv/bot-obormot",
            "DATABASE_PATH": " data/custom.db ",
            "AUDIODOC_URL": " https://audio.test/// ",
            "AUDIODOC_AUDIO_KEY": " whisper-key ",
            "AUDIODOC_DOCUMENT_KEY": " document-key ",
            "AUDIODOC_AUDIO_TIMEOUT": "37",
            "AUDIODOC_DOCUMENT_TIMEOUT": "61",
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
    assert settings.DATABASE_PATH == "/srv/bot-obormot/data/custom.db"
    assert settings.AUDIODOC_URL == "https://audio.test"
    assert settings.AUDIODOC_AUDIO_KEY == "whisper-key"
    assert settings.AUDIODOC_DOCUMENT_KEY == "document-key"
    assert settings.AUDIODOC_AUDIO_TIMEOUT == 37
    assert settings.AUDIODOC_DOCUMENT_TIMEOUT == 61


def test_load_settings_disables_audiodoc_when_no_url_is_configured() -> None:
    """Audiodoc clients remain disabled when neither URL name is configured."""
    settings = load_settings({"SUPERVISOR_ID": "1"})

    assert settings.AUDIODOC_URL == ""
    assert settings.AUDIODOC_AUDIO_KEY == ""
    assert settings.AUDIODOC_DOCUMENT_KEY == ""
    assert settings.AUDIODOC_AUDIO_TIMEOUT == 180
    assert settings.AUDIODOC_DOCUMENT_TIMEOUT == 300


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
        ("AUDIODOC_AUDIO_TIMEOUT", "invalid"),
        ("AUDIODOC_DOCUMENT_TIMEOUT", "invalid"),
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
    """Get settings returns a cached instance until reset."""
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


def test_system_prompt_path_is_optional_and_keeps_the_built_in_prompt() -> None:
    """Without SYSTEM_PROMPT_PATH the packaged prompt is the default."""
    settings = load_settings({"SUPERVISOR_ID": "1"})

    assert settings.SYSTEM_PROMPT_PATH == ""
    assert load_default_system_prompt() == settings.DEFAULT_SYSTEM_PROMPT


def test_system_prompt_path_replaces_the_default_prompt(tmp_path: Path) -> None:
    """A relative path resolves against the home directory and is read as UTF-8."""
    prompt_file = tmp_path / "systemPrompt.md"
    prompt_file.write_text("\n  Свой системный промпт  \n", encoding="utf-8")

    settings = load_settings(
        {
            "SUPERVISOR_ID": "1",
            "BOT_OBORMOT_HOME": str(tmp_path),
            "SYSTEM_PROMPT_PATH": " systemPrompt.md ",
        }
    )

    assert str(prompt_file) == settings.SYSTEM_PROMPT_PATH
    assert settings.DEFAULT_SYSTEM_PROMPT == "Свой системный промпт"


def test_system_prompt_file_is_not_limited_like_personal_prompts(
    tmp_path: Path,
) -> None:
    """The administrator's prompt may be longer than a personal prompt."""
    prompt_file = tmp_path / "long.md"
    prompt_file.write_text("а" * 10000, encoding="utf-8")

    settings = load_settings(
        {"SUPERVISOR_ID": "1", "SYSTEM_PROMPT_PATH": str(prompt_file)}
    )

    assert len(settings.DEFAULT_SYSTEM_PROMPT) == 10000


@pytest.mark.parametrize(
    "content",
    [None, b"", b"  \n\t", b"\xff\xfe\x00"],
    ids=["missing", "empty", "blank", "not-utf8"],
)
def test_system_prompt_path_rejects_unusable_files(
    tmp_path: Path, content: bytes | None
) -> None:
    """A missing, empty or undecodable prompt file is a configuration error."""
    prompt_file = tmp_path / "systemPrompt.md"
    if content is not None:
        prompt_file.write_bytes(content)

    with pytest.raises(ConfigError) as error:
        load_settings({"SUPERVISOR_ID": "1", "SYSTEM_PROMPT_PATH": str(prompt_file)})

    assert [m for m in error.value.errors if "SYSTEM_PROMPT_PATH" in m]
    assert str(prompt_file) in error.value.errors[0]
