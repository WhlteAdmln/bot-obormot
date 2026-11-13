# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

import pytest

from bot.errors import InputTooLongError
from bot.services.validation import (
    MAX_INPUT_TEXT_LENGTH,
    validate_input_text,
)


def test_text_within_limit():
    text = "А" * (MAX_INPUT_TEXT_LENGTH - 1)

    validate_input_text(text)


def test_text_exactly_at_limit():
    text = "А" * MAX_INPUT_TEXT_LENGTH

    validate_input_text(text)


def test_text_exceeding_limit():
    text = "А" * (MAX_INPUT_TEXT_LENGTH + 1)

    with pytest.raises(InputTooLongError):
        validate_input_text(text)


def test_empty_text():
    validate_input_text("")


def test_short_text():
    validate_input_text("Привет! Как дела?")


def test_multiline_text_within_limit():
    text = "Строка\n" * 100

    validate_input_text(text)
