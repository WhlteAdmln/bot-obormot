# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for common validation."""

import pytest

from bot_obormot.common.validation import (
    MAX_INPUT_TEXT_LENGTH,
    validate_input_text,
)
from bot_obormot.errors import InputTooLongError


def test_accepts_text_below_the_limit() -> None:
    text = "А" * (MAX_INPUT_TEXT_LENGTH - 1)

    validate_input_text(text)


def test_accepts_text_exactly_at_the_limit() -> None:
    text = "А" * MAX_INPUT_TEXT_LENGTH

    validate_input_text(text)


def test_rejects_text_over_the_limit() -> None:
    text = "А" * (MAX_INPUT_TEXT_LENGTH + 1)

    with pytest.raises(InputTooLongError) as error:
        validate_input_text(text)

    assert str(error.value) == (
        f"Сообщение слишком длинное (максимум {MAX_INPUT_TEXT_LENGTH} символов)."
    )


def test_accepts_empty_text() -> None:
    validate_input_text("")


def test_accepts_short_text() -> None:
    validate_input_text("Привет! Как дела?")


def test_accepts_multiline_text_below_the_limit() -> None:
    text = "Строка\n" * 100

    validate_input_text(text)
