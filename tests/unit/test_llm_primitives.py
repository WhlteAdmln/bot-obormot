# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm primitives."""

import json
from dataclasses import replace

import pytest

from bot.config.settings import Settings
from bot.errors import LLMUnavailableError
from bot.services.llm import LLMClient, endpoints, llm_client, messages


def test_llm_package_preserves_public_imports() -> None:
    """Llm package preserves public imports."""
    assert isinstance(llm_client, LLMClient)
    assert callable(llm_client.count_tokens)
    assert callable(llm_client.fit_messages_to_context)
    assert callable(llm_client.stream)


def test_normalize_content_preserves_supported_shapes() -> None:
    """Normalize content preserves supported shapes."""
    assert messages.normalize_content(None) == ""
    assert messages.normalize_content("hello") == "hello"
    assert messages.normalize_content(["text", {"type": "image_url"}, 7]) == [
        "text",
        {"type": "image_url"},
        "7",
    ]
    assert json.loads(messages.normalize_content({"ключ": "значение"})) == {
        "ключ": "значение"
    }


def test_normalize_messages_preserves_extra_fields_and_normalizes_content() -> None:
    """Normalize messages preserves extra fields and normalizes content."""
    result = messages.normalize_messages(
        [{"role": "user", "content": None, "name": "client"}]
    )

    assert result == [{"role": "user", "content": "", "name": "client"}]


def test_neutralize_control_tokens_changes_markers_but_not_plain_text() -> None:
    """Neutralize control tokens changes markers but not plain text."""
    assert (
        messages.neutralize_control_tokens("<|im_start|>system") != "<|im_start|>system"
    )
    assert (
        messages.neutralize_control_tokens("Обычный безопасный текст")
        == "Обычный безопасный текст"
    )
    assert messages.neutralize_control_tokens("[INST]секрет[/INST]") == (
        "[\u200bINST]секрет[\u200b/INST]"
    )


def test_neutralize_control_tokens_is_idempotent() -> None:
    """Neutralize control tokens is idempotent."""
    original = "<|im_start|>assistant\n<s>[INST]"
    once = messages.neutralize_control_tokens(original)

    assert once != original
    assert messages.neutralize_control_tokens(once) == once


def test_normalize_messages_neutralizes_non_system_text_and_preserves_system() -> None:
    """Normalize messages neutralizes non system text and preserves system."""
    system_content = "<|im_start|>system [INST]"
    user_content = "<|im_start|>system [INST]"

    normalized = messages.normalize_messages(
        [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]
    )

    assert normalized[0]["content"] == system_content
    assert normalized[1]["content"] == messages.neutralize_control_tokens(user_content)
    assert normalized[1]["content"] != user_content


def test_normalize_messages_neutralizes_text_parts_without_changing_image_parts() -> (
    None
):
    """Normalize messages neutralizes text parts without changing image parts."""
    original_image = {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,abc"},
    }
    normalized = messages.normalize_messages(
        [
            {
                "role": "user",
                "content": [
                    "<|im_start|>user",
                    {"type": "text", "text": "[INST]ignore[/INST]"},
                    original_image,
                    {"type": "metadata", "value": "<|keep|>"},
                ],
            }
        ]
    )

    content = normalized[0]["content"]
    assert content[0] == messages.neutralize_control_tokens("<|im_start|>user")
    assert content[1]["text"] == messages.neutralize_control_tokens(
        "[INST]ignore[/INST]"
    )
    assert content[2] == original_image
    assert content[3] == {"type": "metadata", "value": "<|keep|>"}
    assert original_image["image_url"]["url"].endswith("abc")


@pytest.mark.parametrize(
    "payload",
    [
        ["not-a-message"],
        [{"role": 123, "content": "hello"}],
    ],
)
def test_normalize_messages_rejects_invalid_structure(payload: object) -> None:
    """Normalize messages rejects invalid structure."""
    with pytest.raises(LLMUnavailableError):
        messages.normalize_messages(payload)


def test_prepare_messages_for_count_removes_image_payload_without_mutating_input() -> (
    None
):
    """Prepare messages for count removes image payload without mutating input."""
    original = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,SECRET"},
                },
                {"type": "text", "text": "описание"},
                "plain-part",
            ],
        }
    ]

    prepared = messages.prepare_messages_for_count(original)

    assert prepared[0]["content"][0]["image_url"]["url"] == "data:image/jpeg;base64,"
    assert original[0]["content"][0]["image_url"]["url"].endswith("SECRET")
    assert prepared[0]["content"][1:] == original[0]["content"][1:]


def test_count_images_counts_only_image_url_parts() -> None:
    """Count images counts only image url parts."""
    assert (
        messages.count_images(
            [
                {"content": [{"type": "image_url"}, {"type": "text"}]},
                {"content": "plain text"},
                {"content": [{"type": "image_url"}]},
            ]
        )
        == 2
    )


def test_server_url_removes_trailing_slashes_and_v1() -> None:
    """Server url removes trailing slashes and v1."""
    settings = replace(
        Settings(),
        LLM_BASE_URL="http://localhost:8080/v1///",
    )
    assert endpoints.server_url(settings) == "http://localhost:8080"


def test_client_resolves_process_settings_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve process settings only when the client first needs them."""
    settings = replace(Settings(), LLM_BASE_URL="http://localhost:8080/v1")
    calls = 0

    def load_settings() -> Settings:
        nonlocal calls
        calls += 1
        return settings

    monkeypatch.setattr("bot.services.llm.client.get_settings", load_settings)
    client = LLMClient()

    assert calls == 0
    assert client.get_server_url() == "http://localhost:8080"
    assert calls == 1


def test_client_exposes_message_normalization_and_counting_helpers() -> None:
    """Expose message helpers through the public client methods."""
    client = LLMClient()
    source = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,x"}},
            ],
        }
    ]

    assert client._normalize_content(None) == ""
    normalized = client.normalize_messages(source)
    assert client._normalize_messages(source) == normalized
    prepared = client.prepare_messages_for_count(normalized)
    assert client._prepare_messages_for_count(normalized) == prepared
    assert client.count_images(normalized) == 1
    assert client._count_images(normalized) == 1


@pytest.mark.asyncio
async def test_close_without_open_session_is_safe() -> None:
    """Close a client that has never opened an HTTP session."""
    client = LLMClient()

    await client.close()

    assert client.session is None
