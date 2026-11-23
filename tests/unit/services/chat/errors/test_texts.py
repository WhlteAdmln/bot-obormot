# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for errors texts."""

from bot_obormot.common.validation import MAX_INPUT_TEXT_LENGTH
from bot_obormot.services.chat.errors import texts


def test_user_facing_length_errors_use_configured_input_limit() -> None:
    """User facing length errors use configured input limit."""
    expected_limit = str(MAX_INPUT_TEXT_LENGTH)
    input_message = texts.input_too_long(Exception())
    document_message = texts.document_too_long(Exception())

    assert expected_limit in input_message.replace(" ", "")
    assert expected_limit in document_message.replace(" ", "")
