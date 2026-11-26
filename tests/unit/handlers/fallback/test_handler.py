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
async def test_fallback_denies_unknown_commands_through_dispatcher(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    dispatcher, bot, session = dispatcher_runtime
    user_id, command_text = case

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    expected_texts = ["⛔ Доступ запрещён."]
    assert sent_texts(session) == expected_texts, "access was not denied"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 12, "/unheard_of"),
        (USER_ID + 13, "/unheard_of with trailing words"),
    ],
)
async def test_fallback_does_not_set_commands_for_unknown_commands(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    dispatcher, bot, session = dispatcher_runtime
    user_id, command_text = case

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    assert not any(
        isinstance(request, SetMyCommands) for request in session.requests
    ), "commands were set for an unknown command"
