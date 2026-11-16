# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Validation of user-provided text."""

from bot.errors import InputTooLongError

MAX_INPUT_TEXT_LENGTH = 12288


def validate_input_text(text: str) -> None:
    """Проверяет максимальную длину пользовательского текста."""
    if len(text) > MAX_INPUT_TEXT_LENGTH:
        msg = f"Сообщение слишком длинное (максимум {MAX_INPUT_TEXT_LENGTH} символов)."
        raise InputTooLongError(msg)
