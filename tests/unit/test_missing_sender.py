# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for handlers that receive messages without sender information."""

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot_obormot.handlers.history.basic import (
    cmd_forget_me,
    cmd_history_clear,
    show_history_limit,
)
from bot_obormot.handlers.history.limits import cmd_history_limit
from bot_obormot.handlers.prompt.handler import reset_prompt, save_prompt
from bot_obormot.handlers.start.handler import cmd_start
from tests.support.settings import make_settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler",
    [
        cmd_forget_me,
        cmd_history_clear,
        cmd_start,
        reset_prompt,
        save_prompt,
        show_history_limit,
    ],
)
async def test_handlers_ignore_messages_without_sender(
    handler: Callable[..., Awaitable[None]],
) -> None:
    """Handlers return quietly when Telegram sends no sender information."""
    message = SimpleNamespace(from_user=None, text="prompt", answer=AsyncMock())

    state = SimpleNamespace()
    database = SimpleNamespace()
    settings = make_settings()

    if handler in (cmd_start, show_history_limit):
        await handler(message, state, settings, database)
    else:
        await handler(message, state, database)

    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_limit_command_ignores_messages_without_sender() -> None:
    """The history limit command returns quietly without a sender."""
    message = SimpleNamespace(from_user=None, answer=AsyncMock())

    await cmd_history_limit(
        message,
        SimpleNamespace(),
        SimpleNamespace(args="5"),
        make_settings(),
        SimpleNamespace(),
    )

    message.answer.assert_not_awaited()
