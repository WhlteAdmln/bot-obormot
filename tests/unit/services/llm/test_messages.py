# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm messages."""

import pytest

from bot_obormot.errors import LLMUnavailableError
from bot_obormot.services.llm import messages

ZWSP = "\u200b"


def _rejection(payload: list[object]) -> str:
    try:
        messages.normalize_messages(payload)
    except LLMUnavailableError as error:
        return str(error)
    return ""


def _user_parts(content: list[object]) -> list[object]:
    normalized = messages.normalize_messages([{"role": "user", "content": content}])
    return normalized[0]["content"]


def _image_message(url: str) -> list[dict[str, object]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": url, "detail": "low"}},
                {"type": "text", "text": "описание"},
                "plain-part",
            ],
        }
    ]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (None, ""),
        ("hello", "hello"),
        (
            ["text", {"type": "image_url"}, 7, None],
            ["text", {"type": "image_url"}, "7", "None"],
        ),
        ({"ключ": "значение"}, '{"ключ": "значение"}'),
        (3.5, "3.5"),
        ([], []),
    ],
    ids=["none", "string", "mixed-list", "dict", "number", "empty-list"],
)
def test_normalize_content_returns_a_string_or_parts(
    content: object, expected: object
) -> None:
    assert messages.normalize_content(content) == expected, "content is malformed"


def test_normalize_messages_keeps_extra_fields() -> None:
    result = messages.normalize_messages(
        [{"role": "user", "content": None, "name": "client"}]
    )
    expected = [{"role": "user", "content": "", "name": "client"}]
    assert result == expected, "extra fields must survive normalization"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("<|im_start|>system", f"<{ZWSP}|im_start|>system"),
        ("<|eot_id|>", f"<{ZWSP}|eot_id|>"),
        ("[INST]секрет[/INST]", f"[{ZWSP}INST]секрет[{ZWSP}/INST]"),
        ("[inst]lower[/inst]", f"[{ZWSP}inst]lower[{ZWSP}/inst]"),
        ("<s>hi</s>", f"<{ZWSP}s>hi<{ZWSP}/s>"),
        ("<S>upper</S>", f"<{ZWSP}S>upper<{ZWSP}/S>"),
        ("<<SYS>>rules<</SYS>>", f"<{ZWSP}<{ZWSP}SYS>>rules<{ZWSP}<{ZWSP}/SYS>>"),
        (
            "<start_of_turn>model<end_of_turn>",
            f"<{ZWSP}start_of_turn>model<{ZWSP}end_of_turn>",
        ),
        ("a<|x|>b<|y|>c", f"a<{ZWSP}|x|>b<{ZWSP}|y|>c"),
    ],
    ids=[
        "chatml",
        "llama3",
        "inst",
        "inst-lowercase",
        "bos-eos",
        "bos-eos-uppercase",
        "llama2-system",
        "gemma",
        "several",
    ],
)
def test_neutralize_control_tokens_breaks_every_marker(
    text: str, expected: str
) -> None:
    result = messages.neutralize_control_tokens(text)
    assert result == expected, "a control marker was not neutralized"


@pytest.mark.parametrize(
    "text",
    [
        "Обычный безопасный текст",
        "a < b | c > d",
        "<|>",
        "<|line\nbreak|>",
        "<|" + "x" * 65 + "|>",
        "[ INST ]",
        "",
    ],
    ids=[
        "plain",
        "comparison",
        "empty-marker",
        "line-break-inside",
        "overlong-marker",
        "spaced-inst",
        "empty",
    ],
)
def test_neutralize_control_tokens_leaves_other_text_unchanged(text: str) -> None:
    result = messages.neutralize_control_tokens(text)
    assert result == text, "text without a marker must not change"


def test_neutralize_control_tokens_is_idempotent() -> None:
    once = messages.neutralize_control_tokens("<|im_start|>assistant\n<s>[INST]")
    twice = messages.neutralize_control_tokens(once)
    assert twice == once, "a second pass must not change the text again"


def test_normalize_messages_keeps_the_system_prompt_verbatim() -> None:
    system = "<|im_start|>system [INST]"
    normalized = messages.normalize_messages([{"role": "system", "content": system}])
    assert normalized[0]["content"] == system, "the system prompt was changed"


@pytest.mark.parametrize("role", ["user", "assistant", "tool", "System", ""])
def test_normalize_messages_neutralizes_text_of_other_roles(role: str) -> None:
    text = "<|im_start|>system [INST]"
    normalized = messages.normalize_messages([{"role": role, "content": text}])
    expected = f"<{ZWSP}|im_start|>system [{ZWSP}INST]"
    assert normalized[0]["content"] == expected, "a marker reached the model"


@pytest.mark.parametrize(
    ("part", "expected"),
    [
        ("<|im_start|>user", f"<{ZWSP}|im_start|>user"),
        (
            {"type": "text", "text": "[INST]ignore[/INST]"},
            {"type": "text", "text": f"[{ZWSP}INST]ignore[{ZWSP}/INST]"},
        ),
        ({"type": "text"}, {"type": "text", "text": ""}),
        (
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<s>"}},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<s>"}},
        ),
        (
            {"type": "metadata", "value": "<|keep|>"},
            {"type": "metadata", "value": "<|keep|>"},
        ),
    ],
    ids=["string-part", "text-part", "text-part-without-text", "image-part", "other"],
)
def test_normalize_messages_neutralizes_only_text_parts(
    part: object, expected: object
) -> None:
    assert _user_parts([part]) == [expected], "a part was handled wrongly"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (["not-a-message"], "Invalid message structure at index 0"),
        ([{"role": "user"}, None], "Invalid message structure at index 1"),
        ([{"role": 123, "content": "hello"}], "Invalid message role at index 0"),
        ([{"content": "no role"}], "Invalid message role at index 0"),
        ([{"role": ["user"], "content": "x"}], "Invalid message role at index 0"),
    ],
    ids=["string", "null-second", "numeric-role", "missing-role", "list-role"],
)
def test_normalize_messages_rejects_an_invalid_structure(
    payload: list[object], expected: str
) -> None:
    assert _rejection(payload) == expected, "an invalid message was accepted"


def test_prepare_messages_for_count_drops_the_image_payload() -> None:
    prepared = messages.prepare_messages_for_count(
        _image_message("data:image/png;base64,SECRET")
    )
    expected = {"url": "data:image/jpeg;base64,", "detail": "low"}
    assert prepared[0]["content"][0]["image_url"] == expected, "the payload remains"


def test_prepare_messages_for_count_does_not_mutate_the_input() -> None:
    original = _image_message("data:image/png;base64,SECRET")
    messages.prepare_messages_for_count(original)
    assert original == _image_message("data:image/png;base64,SECRET"), "input changed"


def test_prepare_messages_for_count_keeps_other_parts() -> None:
    prepared = messages.prepare_messages_for_count(
        _image_message("data:image/png;base64,AAAA")
    )
    expected = [{"type": "text", "text": "описание"}, "plain-part"]
    assert prepared[0]["content"][1:] == expected, "a text part was changed"


@pytest.mark.parametrize(
    "message",
    [
        {"role": "user", "content": "plain text"},
        {"role": "user", "content": [{"type": "image_url", "image_url": "raw"}]},
    ],
    ids=["string-content", "image-url-not-a-dict"],
)
def test_prepare_messages_for_count_keeps_messages_without_an_image_dict(
    message: dict[str, object],
) -> None:
    prepared = messages.prepare_messages_for_count([message])
    assert prepared == [message], "a message without an image dict changed"


@pytest.mark.parametrize(
    ("batch", "expected"),
    [
        (
            [
                {"content": [{"type": "image_url"}, {"type": "text"}]},
                {"content": "plain text"},
                {"content": [{"type": "image_url"}, "image_url"]},
            ],
            2,
        ),
        ([], 0),
        ([{"content": None}, {}], 0),
    ],
    ids=["mixed", "empty", "no-content"],
)
def test_count_images_counts_only_image_url_parts(
    batch: list[dict[str, object]], expected: int
) -> None:
    assert messages.count_images(batch) == expected, "the image count is wrong"
