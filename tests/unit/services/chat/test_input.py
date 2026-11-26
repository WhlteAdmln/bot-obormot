# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat input."""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from bot_obormot.services.chat import input as chat_input
from bot_obormot.services.chat.input import (
    MessageInfo,
    PreparedMessage,
    inspect_message,
    prepare_message,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    ("name", "expected"),
    [("MessageInfo", MessageInfo), ("PreparedMessage", PreparedMessage)],
)
def test_reexports_the_public_models(name: str, expected: type) -> None:
    exported = getattr(chat_input, name)
    assert exported is expected, f"chat input does not reexport {name}"


@pytest.mark.parametrize("name", ["inspect_message", "prepare_message"])
def test_reexports_the_public_functions(name: str) -> None:
    exported = getattr(chat_input, name)
    assert exported.__name__ == name, f"chat input reexports another {name}"


@pytest.mark.parametrize(
    ("function", "expected"),
    [
        (inspect_message, ["message"]),
        (
            prepare_message,
            [
                "message",
                "info",
                "text_override",
                "settings",
                "downloader",
                "media_slots",
            ],
        ),
    ],
)
def test_keeps_the_original_function_signatures(
    function: Callable[..., object], expected: list[str]
) -> None:
    parameters = list(inspect.signature(function).parameters)
    assert parameters == expected, f"the signature of {function.__name__} changed"
