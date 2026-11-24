# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for common validation."""

import pytest

from bot_obormot.common.validation import (
    MAX_INPUT_TEXT_LENGTH,
    validate_input_text,
)
from bot_obormot.errors import InputTooLongError


def _rejection(text: str) -> str:
    try:
        validate_input_text(text)
    except InputTooLongError as error:
        return str(error)
    return ""


@pytest.mark.parametrize(
    "text",
    [
        "А" * (MAX_INPUT_TEXT_LENGTH - 1),
        "Я" * MAX_INPUT_TEXT_LENGTH,
        "",
        "Привет! Как дела?",
        "Строка\n" * 100,
        "😀" * MAX_INPUT_TEXT_LENGTH,
        "\x00\u202e\r\n" * (MAX_INPUT_TEXT_LENGTH // 4),
    ],
    ids=[
        "below-limit",
        "at-limit",
        "empty",
        "short",
        "multiline",
        "astral-at-limit",
        "control-characters-at-limit",
    ],
)
def test_accepts_text_up_to_the_limit(text: str) -> None:
    expected = ""
    assert _rejection(text) == expected, "text within the limit must be accepted"


@pytest.mark.parametrize(
    "text",
    [
        "А" * (MAX_INPUT_TEXT_LENGTH + 1),
        "\n" * (MAX_INPUT_TEXT_LENGTH + 1),
        "x" * (MAX_INPUT_TEXT_LENGTH * 50),
    ],
    ids=["one-over", "line-breaks-over", "far-over"],
)
def test_rejects_text_over_the_limit(text: str) -> None:
    expected = f"Сообщение слишком длинное (максимум {MAX_INPUT_TEXT_LENGTH} символов)."
    assert _rejection(text) == expected, "text over the limit must be rejected"
