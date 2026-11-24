# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for fallback handler."""

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import (
    SetMyCommands,
)

from tests.support.dispatcher import USER_ID, sent_texts
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
    make_update,
)


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 10, "/not_registered"),
        (USER_ID + 11, "/not_registered unexpected arguments"),
    ],
)
async def test_fallback_handles_unknown_commands_through_dispatcher(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    dispatcher, bot, session = dispatcher_runtime
    user_id, command_text = case

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    assert sent_texts(session) == ["⛔ Доступ запрещён."]
    assert not any(isinstance(request, SetMyCommands) for request in session.requests)
