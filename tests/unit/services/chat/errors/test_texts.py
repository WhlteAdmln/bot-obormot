# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for errors texts."""

from bot_obormot.common.validation import MAX_INPUT_TEXT_LENGTH
from bot_obormot.services.chat.errors import texts


def test_input_too_long_message_names_the_input_limit() -> None:
    expected_limit = str(MAX_INPUT_TEXT_LENGTH)
    message = texts.input_too_long(ValueError("input of 99999 characters"))
    assert expected_limit in message.replace(" ", ""), (
        "the input error does not name the limit"
    )


def test_document_too_long_message_names_the_input_limit() -> None:
    expected_limit = str(MAX_INPUT_TEXT_LENGTH)
    message = texts.document_too_long(RuntimeError("document truncated"))
    assert expected_limit in message.replace(" ", ""), (
        "the document error does not name the limit"
    )
