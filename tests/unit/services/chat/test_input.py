# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat input."""

from __future__ import annotations

import inspect

from bot_obormot.services.chat import input as chat_input
from bot_obormot.services.chat.input import (
    MessageInfo,
    PreparedMessage,
    inspect_message,
    prepare_message,
)


def test_new_chat_input_package_reexports_the_public_api() -> None:
    assert chat_input.MessageInfo is MessageInfo
    assert chat_input.PreparedMessage is PreparedMessage
    expected_name = "inspect_message"
    assert chat_input.inspect_message.__name__ == expected_name
    expected_name = "prepare_message"
    assert chat_input.prepare_message.__name__ == expected_name


def test_public_api_keeps_original_function_signatures() -> None:
    assert list(inspect.signature(inspect_message).parameters) == ["message"]
    assert list(inspect.signature(prepare_message).parameters) == [
        "message",
        "info",
        "text_override",
        "settings",
    ]
