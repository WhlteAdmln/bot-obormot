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
    callbacks = [
        handler.callback for handler in history_basic.create_router().message.handlers
    ]
    assert cmd_forget_me in callbacks, "forget_me is not registered"


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


def _denied_settings(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Deny access to users who are not explicitly allowed."""
    dispatcher_runtime[0].workflow_data["settings"] = replace(
        SETTINGS, ALLOW_ALL_USERS=False
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "command_text", "expected_text"),
    [
        (HISTORY_USER_ID + 10, "/history_clear extra", "🧹 История диалога очищена."),
        (HISTORY_USER_ID + 11, "/forget_me extra", "🧹 Все твои данные удалены."),
        (
            HISTORY_USER_ID + 12,
            "/history extra",
            (
                f"📚 Твой лимит истории: 17 полных обменов.\n"
                f"Стандартный лимит: {SETTINGS.DEFAULT_HISTORY_EXCHANGES}."
            ),
        ),
    ],
)
async def test_runs_basic_history_commands_through_dispatcher(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    user_id: int,
    command_text: str,
    expected_text: str,
) -> None:
    access_database.history_limits[user_id] = 17

    session = await feed_command(dispatcher_runtime, user_id, command_text)

    assert sent_texts(session) == [expected_text], "the command reply differs"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "command_text", "operation"),
    [
        (HISTORY_USER_ID + 13, "/history_clear extra", "reset_history"),
        (HISTORY_USER_ID + 14, "/forget_me extra", "forget_user"),
    ],
)
async def test_basic_history_commands_update_the_database(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    user_id: int,
    command_text: str,
    operation: str,
) -> None:
    access_database.history_limits[user_id] = 19

    await feed_command(dispatcher_runtime, user_id, command_text)

    expected_calls = [(user_id,)]
    calls = access_database.log.arguments(operation)
    assert calls == expected_calls, f"{operation} was not called for the user"


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

    expected_empty: list[str] = []
    sent = sent_texts(dispatcher_runtime[2])
    assert sent == expected_empty, "a reply was sent despite the failure"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    ("user_id", "command_text"),
    [
        (HISTORY_USER_ID + 90, "/history"),
        (HISTORY_USER_ID + 91, "/history_clear"),
        (HISTORY_USER_ID + 92, "/forget_me"),
        (HISTORY_USER_ID + 93, "/history_limit 10"),
    ],
)
async def test_history_commands_are_denied_without_access(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    user_id: int,
    command_text: str,
) -> None:
    _denied_settings(dispatcher_runtime)

    session = await feed_command(dispatcher_runtime, user_id, command_text)

    expected_texts = ["⛔ У тебя нет доступа к этому боту."]
    assert sent_texts(session) == expected_texts, "access was not denied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "command_text"),
    [
        (HISTORY_USER_ID + 94, "/history"),
        (HISTORY_USER_ID + 95, "/history_clear"),
        (HISTORY_USER_ID + 96, "/forget_me"),
        (HISTORY_USER_ID + 97, "/history_limit 12"),
    ],
)
async def test_denied_history_commands_do_not_write_to_the_database(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    user_id: int,
    command_text: str,
) -> None:
    _denied_settings(dispatcher_runtime)

    await feed_command(dispatcher_runtime, user_id, command_text)

    operations = ("reset_history", "forget_user", "set_history_limit")
    expected_calls: dict[str, list[tuple[object, ...]]] = {
        operation: [] for operation in operations
    }
    calls = {
        operation: access_database.log.arguments(operation) for operation in operations
    }
    assert calls == expected_calls, "a denied command wrote to the database"


@pytest.mark.asyncio
async def test_denied_history_command_does_not_read_the_limit(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = HISTORY_USER_ID + 98
    _denied_settings(dispatcher_runtime)

    await feed_command(dispatcher_runtime, user_id, "/history")

    limit = access_database.history_limits.get(user_id)
    assert limit is None, "a denied user got a history limit"
