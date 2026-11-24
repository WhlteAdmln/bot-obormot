# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm messages."""

import json

import pytest

from bot_obormot.errors import LLMUnavailableError
from bot_obormot.services.llm import messages


def test_normalize_content_preserves_supported_shapes() -> None:
    expected_empty = ""
    assert messages.normalize_content(None) == expected_empty, (
        "expected an empty string"
    )
    expected_normalize_content = "hello"
    assert messages.normalize_content("hello") == expected_normalize_content
    assert messages.normalize_content(["text", {"type": "image_url"}, 7]) == [
        "text",
        {"type": "image_url"},
        "7",
    ]
    assert json.loads(messages.normalize_content({"ключ": "значение"})) == {
        "ключ": "значение"
    }


def test_normalize_messages_preserves_extra_fields_and_normalizes_content() -> None:
    result = messages.normalize_messages(
        [{"role": "user", "content": None, "name": "client"}]
    )

    assert result == [{"role": "user", "content": "", "name": "client"}]


def test_neutralize_control_tokens_changes_markers_but_not_plain_text() -> None:
    expected_text = "<|im_start|>system"
    assert messages.neutralize_control_tokens("<|im_start|>system") != expected_text
    expected_text = "Обычный безопасный текст"
    assert (
        messages.neutralize_control_tokens("Обычный безопасный текст") == expected_text
    )
    expected_text = "[\u200bINST]секрет[\u200b/INST]"
    assert messages.neutralize_control_tokens("[INST]секрет[/INST]") == expected_text


def test_neutralize_control_tokens_is_idempotent() -> None:
    original = "<|im_start|>assistant\n<s>[INST]"
    once = messages.neutralize_control_tokens(original)

    assert once != original
    assert messages.neutralize_control_tokens(once) == once


def test_normalize_messages_neutralizes_non_system_text_and_preserves_system() -> None:
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
    with pytest.raises(LLMUnavailableError):
        messages.normalize_messages(payload)


def test_prepare_messages_for_count_removes_image_payload_without_mutating_input() -> (
    None
):
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

    expected_url = "data:image/jpeg;base64,"
    assert prepared[0]["content"][0]["image_url"]["url"] == expected_url
    assert original[0]["content"][0]["image_url"]["url"].endswith("SECRET")
    assert prepared[0]["content"][1:] == original[0]["content"][1:]


def test_count_images_counts_only_image_url_parts() -> None:
    expected_count_images = 2
    assert (
        messages.count_images(
            [
                {"content": [{"type": "image_url"}, {"type": "text"}]},
                {"content": "plain text"},
                {"content": [{"type": "image_url"}]},
            ]
        )
        == expected_count_images
    )
