# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for history basic."""

from collections.abc import Awaitable, Callable
from dataclasses import replace
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher

from bot_obormot.handlers.history import basic as history_basic
from bot_obormot.handlers.history.basic import (
    cmd_forget_me,
    cmd_history_clear,
    show_history_limit,
)
from bot_obormot.handlers.prompt.handler import reset_prompt, save_prompt
from bot_obormot.handlers.start.handler import cmd_start
from tests.support.dispatcher import (
    HISTORY_USER_ID,
    SETTINGS,
    AccessDatabase,
    feed_command,
    sent_texts,
)
from tests.support.handler_messages import FakeMessage
from tests.support.settings import make_settings
from tests.support.telegram import (
    FakeTelegramSession,
)


def test_forget_me_command_is_registered() -> None:
    assert any(
        handler.callback is cmd_forget_me
        for handler in history_basic.router.message.handlers
    )


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
    message = FakeMessage(None, "Будь краток")

    state = SimpleNamespace()
    database = SimpleNamespace()
    settings = make_settings()

    if handler in (cmd_start, show_history_limit):
        await handler(message, state, settings, database)
    else:
        await handler(message, state, database)

    expected_empty: list[str] = []
    assert message.answers == expected_empty, "answered a message without sender"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 10, "/history_clear extra", "clear"),
        (HISTORY_USER_ID + 11, "/forget_me extra", "forget"),
        (HISTORY_USER_ID + 12, "/history extra", "show"),
    ],
)
async def test_runs_basic_history_commands_through_dispatcher(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    user_id, command_text, operation = case
    access_database.history_limits[user_id] = 17

    session = await feed_command(dispatcher_runtime, user_id, command_text)

    clear_operation = "clear"
    forget_operation = "forget"
    if operation == clear_operation:
        expected_text = "🧹 История диалога очищена."
        assert access_database.log.arguments("reset_history") == [(user_id,)]
    elif operation == forget_operation:
        expected_text = "🧹 Все твои данные удалены."
        assert access_database.log.arguments("forget_user") == [(user_id,)]
    else:
        expected_text = (
            f"📚 Твой лимит истории: 17 полных обменов.\n"
            f"Стандартный лимит: {SETTINGS.DEFAULT_HISTORY_EXCHANGES}."
        )

    assert sent_texts(session) == [expected_text]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 20, "/history_clear", "reset_history"),
        (HISTORY_USER_ID + 21, "/forget_me", "forget_user"),
        (HISTORY_USER_ID + 22, "/history", "get_history_limit"),
    ],
)
async def test_history_basic_commands_propagate_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    user_id, command_text, failed_operation = case
    access_database.scenario.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, user_id, command_text)

    assert sent_texts(dispatcher_runtime[2]) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 90, "/history", "show"),
        (HISTORY_USER_ID + 91, "/history_clear", "clear"),
        (HISTORY_USER_ID + 92, "/forget_me", "forget"),
        (HISTORY_USER_ID + 93, "/history_limit 10", "limit"),
    ],
)
async def test_history_commands_are_denied_without_access(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    user_id, command_text, operation = case
    dispatcher_runtime[0].workflow_data["settings"] = replace(
        SETTINGS, ALLOW_ALL_USERS=False
    )

    session = await feed_command(dispatcher_runtime, user_id, command_text)

    assert sent_texts(session) == ["⛔ У тебя нет доступа к этому боту."]
    assert access_database.log.arguments("reset_history") == []
    assert access_database.log.arguments("forget_user") == []
    assert access_database.log.arguments("set_history_limit") == []
    expected_operation = "show"
    if operation == expected_operation:
        assert access_database.history_limits.get(user_id) is None
