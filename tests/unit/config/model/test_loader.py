# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the settings loader."""

from pathlib import Path

import pytest

from bot_obormot.config import load_default_system_prompt
from bot_obormot.config.model.loader import ConfigError, load_settings


def _full_environ() -> dict[str, str]:
    return {
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


def _invalid_environ() -> dict[str, str]:
    return {
        "SUPERVISOR_ID": "invalid",
        "ADMIN_IDS": "bad-id",
        "ALLOWED_USERS": "-1",
        "ALLOW_ALL_USERS": "maybe",
        "LLM_TEMPERATURE": "nan",
        "LLM_TOP_P": "2",
        "LLM_TOKEN_COUNTING": "unknown",
        "DATABASE_PATH": " ",
    }


def _write_prompt(prompt_file: Path, content: bytes | None) -> None:
    if content is not None:
        prompt_file.write_bytes(content)


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("BOT_TOKEN", "test-token"),
        ("SUPERVISOR_ID", 42),
        ("ADMIN_IDS", {10, 20}),
        ("ALLOWED_USERS", {30}),
        ("ALLOW_ALL_USERS", True),
        ("LLM_BASE_URL", "http://llm.test/v1"),
        ("LLM_TEMPERATURE", 0.2),
        ("LLM_TOP_P", 1.0),
        ("LLM_CONTEXT_SIZE", 8192),
        ("LLM_TOKEN_COUNTING", "estimate"),
        ("DATABASE_PATH", "/srv/bot-obormot/data/custom.db"),
        ("AUDIODOC_URL", "https://audio.test"),
        ("AUDIODOC_AUDIO_KEY", "whisper-key"),
        ("AUDIODOC_DOCUMENT_KEY", "document-key"),
        ("AUDIODOC_AUDIO_TIMEOUT", 37),
        ("AUDIODOC_DOCUMENT_TIMEOUT", 61),
    ],
)
def test_load_settings_uses_the_supplied_environment(
    attribute: str, expected: object
) -> None:
    settings = load_settings(_full_environ())
    actual = getattr(settings, attribute)
    assert actual == expected, f"{attribute} does not match the environment"


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("AUDIODOC_URL", ""),
        ("AUDIODOC_AUDIO_KEY", ""),
        ("AUDIODOC_DOCUMENT_KEY", ""),
        ("AUDIODOC_AUDIO_TIMEOUT", 180),
        ("AUDIODOC_DOCUMENT_TIMEOUT", 300),
    ],
)
def test_load_settings_disables_audiodoc_when_no_url_is_configured(
    attribute: str, expected: object
) -> None:
    environ = {"SUPERVISOR_ID": "1"}
    settings = load_settings(environ)
    actual = getattr(settings, attribute)
    assert actual == expected, f"{attribute} is not the disabled default"


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
    with pytest.raises(ConfigError) as error:
        load_settings({"SUPERVISOR_ID": "1", name: value})

    named = any(name in message for message in error.value.errors)
    assert named, f"no error names {name}"


def test_load_settings_reports_one_error_per_invalid_setting() -> None:
    environ = _invalid_environ()

    with pytest.raises(ConfigError) as error:
        load_settings(environ)

    assert len(error.value.errors) == len(environ), "the error count is wrong"


@pytest.mark.parametrize("name", list(_invalid_environ()))
def test_load_settings_names_each_invalid_setting(name: str) -> None:
    environ = _invalid_environ()

    with pytest.raises(ConfigError) as error:
        load_settings(environ)

    assert name in str(error.value), f"the combined error does not name {name}"


def test_system_prompt_path_is_optional() -> None:
    environ = {"SUPERVISOR_ID": "1"}
    settings = load_settings(environ)
    expected_empty = ""
    assert expected_empty == settings.SYSTEM_PROMPT_PATH, "expected an empty string"


def test_missing_system_prompt_path_keeps_the_built_in_prompt() -> None:
    environ = {"SUPERVISOR_ID": "7"}
    settings = load_settings(environ)
    expected_prompt = load_default_system_prompt()
    assert expected_prompt == settings.DEFAULT_SYSTEM_PROMPT, "the prompt changed"


def test_system_prompt_path_resolves_against_the_home(tmp_path: Path) -> None:
    prompt_file = tmp_path / "systemPrompt.md"
    prompt_file.write_text("\n  Свой системный промпт  \n", encoding="utf-8")

    settings = load_settings(
        {
            "SUPERVISOR_ID": "1",
            "BOT_OBORMOT_HOME": str(tmp_path),
            "SYSTEM_PROMPT_PATH": " systemPrompt.md ",
        }
    )

    expected_path = str(prompt_file)
    assert expected_path == settings.SYSTEM_PROMPT_PATH, "the path was not resolved"


def test_system_prompt_path_replaces_the_default_prompt(tmp_path: Path) -> None:
    prompt_file = tmp_path / "custom-prompt.md"
    prompt_file.write_text("\n\t Другой промпт для бота \n", encoding="utf-8")

    settings = load_settings(
        {
            "SUPERVISOR_ID": "3",
            "BOT_OBORMOT_HOME": str(tmp_path),
            "SYSTEM_PROMPT_PATH": "custom-prompt.md",
        }
    )

    expected_prompt = "Другой промпт для бота"
    assert expected_prompt == settings.DEFAULT_SYSTEM_PROMPT, "the prompt was not read"


def test_system_prompt_file_is_not_limited_like_personal_prompts(
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "long.md"
    prompt_file.write_text("а" * 10000, encoding="utf-8")

    settings = load_settings(
        {"SUPERVISOR_ID": "1", "SYSTEM_PROMPT_PATH": str(prompt_file)}
    )

    expected_count = 10000
    actual_count = len(settings.DEFAULT_SYSTEM_PROMPT)
    assert actual_count == expected_count, "the system prompt was truncated"


@pytest.mark.parametrize(
    "content",
    [None, b"", b"  \n\t", b"\xff\xfe\x00"],
    ids=["missing", "empty", "blank", "not-utf8"],
)
def test_system_prompt_path_rejects_unusable_files(
    tmp_path: Path, content: bytes | None
) -> None:
    prompt_file = tmp_path / "systemPrompt.md"
    _write_prompt(prompt_file, content)

    with pytest.raises(ConfigError) as error:
        load_settings({"SUPERVISOR_ID": "1", "SYSTEM_PROMPT_PATH": str(prompt_file)})

    setting_name = "SYSTEM_PROMPT_PATH"
    mentions = [m for m in error.value.errors if setting_name in m]
    expected_empty: list[str] = []
    assert mentions != expected_empty, "no error names the setting"


@pytest.mark.parametrize(
    "content",
    [None, b"", b" \r\n ", b"\xc3\x28\xa0"],
    ids=["missing", "empty", "blank", "not-utf8"],
)
def test_system_prompt_error_names_the_unusable_file(
    tmp_path: Path, content: bytes | None
) -> None:
    prompt_file = tmp_path / "broken-prompt.md"
    _write_prompt(prompt_file, content)

    with pytest.raises(ConfigError) as error:
        load_settings({"SUPERVISOR_ID": "2", "SYSTEM_PROMPT_PATH": str(prompt_file)})

    assert str(prompt_file) in error.value.errors[0], "the error does not name the file"
