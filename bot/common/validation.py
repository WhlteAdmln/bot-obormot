# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Validation of user-provided text."""

from bot.common.texts import INPUT_TOO_LONG_MESSAGE
from bot.errors import InputTooLongError

MAX_INPUT_TEXT_LENGTH = 12288


def validate_input_text(text: str) -> None:
    """Validate the maximum length of user-provided text."""
    if len(text) > MAX_INPUT_TEXT_LENGTH:
        msg = INPUT_TOO_LONG_MESSAGE.format(max_length=MAX_INPUT_TEXT_LENGTH)
        raise InputTooLongError(msg)
