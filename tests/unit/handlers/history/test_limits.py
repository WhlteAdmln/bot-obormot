# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for history limits."""

import logging
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher

from bot_obormot.handlers.history import limits as history_limits_handler
from bot_obormot.handlers.history.limits import cmd_history_limit
from tests.support.dispatcher import (
    HISTORY_ADMIN_ID,
    HISTORY_USER_ID,
    SETTINGS,
    SUPERVISOR_ID,
    AccessDatabase,
    feed_command,
    sent_texts,
)
from tests.support.handler_messages import SETTINGS as AUDIT_SETTINGS
from tests.support.handler_messages import FakeMessage
from tests.support.settings import make_settings
from tests.support.telegram import (
    FakeTelegramSession,
)

HISTORY_TARGET_ID = 444000002


@pytest.mark.asyncio
async def test_history_limit_for_another_user_is_audited(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """History limit for another user is audited."""
    actor_id = AUDIT_SETTINGS.SUPERVISOR_ID
    target_id = 123456789
    exchange_limit = 35
    calls = []

    async def set_history_limit(user_id: int, limit: int | None) -> None:
        calls.append((user_id, limit))

    async def send_prompt_status(_message: object, _state: object, _text: str) -> None:
        return None

    database = SimpleNamespace(set_history_limit=set_history_limit)
    monkeypatch.setattr(
        history_limits_handler,
        "send_prompt_status",
        send_prompt_status,
    )
    message = FakeMessage(actor_id)
    state = SimpleNamespace()
    command = SimpleNamespace(args=f"{target_id} {exchange_limit}")

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await history_limits_handler.cmd_history_limit(
            message, state, command, AUDIT_SETTINGS, database
        )

    assert calls == [(target_id, exchange_limit)]
    assert (
        f"AUDIT action=history_limit_set actor={actor_id} "
        f"target={target_id} result={exchange_limit}"
    ) in caplog.text


@pytest.mark.asyncio
async def test_history_limit_command_ignores_messages_without_sender() -> None:
    """The history limit command returns quietly without a sender."""
    message = FakeMessage(None, "/history_limit 5")

    await cmd_history_limit(
        message,
        SimpleNamespace(),
        SimpleNamespace(args="5"),
        make_settings(),
        SimpleNamespace(),
    )

    expected_empty: list[str] = []
    assert message.answers == expected_empty, "answered a message without sender"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_without_arguments_shows_usage(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """History limit without arguments displays command usage."""
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 30,
        "/history_limit",
    )

    assert sent_texts(session) == [
        (
            "Использование:\n"
            "/history — показать текущий лимит\n"
            "/history_limit 20 — установить свой лимит\n"
            "/history_limit ID 100 — установить лимит другому пользователю "
            "(только администратор)."
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 31, set(), 12),
        (HISTORY_ADMIN_ID, {HISTORY_ADMIN_ID}, SETTINGS.MAX_HISTORY_EXCHANGES),
        (SUPERVISOR_ID, set(), SETTINGS.MAX_HISTORY_EXCHANGES),
    ],
)
async def test_history_limit_sets_own_limit_for_user_admin_and_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], int],
) -> None:
    """Users, administrators and supervisor can set their own limit."""
    user_id, admin_ids, limit = case
    access_database.admin_ids = admin_ids

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {limit}",
    )

    assert sent_texts(session) == [
        f"✅ Твой лимит истории установлен: {limit} полных обменов."
    ]
    assert access_database.log.arguments("set_history_limit") == [(user_id, limit)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (
            HISTORY_USER_ID + 40,
            "invalid",
            "⚠️ Укажи целое число.\nПример: /history_limit 20",
        ),
        (
            HISTORY_USER_ID + 41,
            "0",
            f"⚠️ Допустимый лимит: от 1 до {SETTINGS.DEFAULT_HISTORY_EXCHANGES}.",
        ),
        (
            HISTORY_USER_ID + 42,
            str(SETTINGS.DEFAULT_HISTORY_EXCHANGES + 1),
            f"⚠️ Допустимый лимит: от 1 до {SETTINGS.DEFAULT_HISTORY_EXCHANGES}.",
        ),
    ],
)
async def test_history_limit_rejects_invalid_own_limits(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Invalid own limit arguments are rejected with the exact response."""
    user_id, raw_limit, expected_text = case

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {raw_limit}",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.log.arguments("set_history_limit") == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_denies_non_admin_target_changes(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Regular users cannot change another user's history limit."""
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 50,
        f"/history_limit {HISTORY_TARGET_ID} 10",
    )

    assert sent_texts(session) == [
        "⛔ Назначать лимиты другим пользователям могут только администраторы."
    ]


@pytest.mark.asyncio
async def test_history_limit_allows_admin_to_change_target_limit(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """An administrator can set another user's history limit."""
    user_id = HISTORY_ADMIN_ID + 1
    limit = 25
    access_database.admin_ids = {user_id}

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {HISTORY_TARGET_ID} {limit}",
    )

    assert sent_texts(session) == [
        (
            f"✅ Для пользователя {HISTORY_TARGET_ID} установлен лимит "
            f"{limit} полных обменов."
        )
    ]
    assert access_database.log.arguments("set_history_limit") == [
        (HISTORY_TARGET_ID, limit)
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (
            HISTORY_ADMIN_ID + 2,
            "invalid 10",
            "⚠️ Укажи корректный ID пользователя и целое число лимита.",
        ),
        (
            HISTORY_ADMIN_ID + 3,
            "0 10",
            "⚠️ ID пользователя должен быть положительным.",
        ),
        (
            HISTORY_ADMIN_ID + 4,
            f"{HISTORY_TARGET_ID} invalid",
            "⚠️ Укажи корректный ID пользователя и целое число лимита.",
        ),
        (
            HISTORY_ADMIN_ID + 5,
            f"{HISTORY_TARGET_ID} 0",
            f"⚠️ Допустимый лимит: от 1 до {SETTINGS.MAX_HISTORY_EXCHANGES}.",
        ),
    ],
)
async def test_history_limit_rejects_invalid_target_arguments(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """Invalid target IDs and limits are rejected."""
    user_id, arguments, expected_text = case
    access_database.admin_ids = {user_id}

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {arguments}",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.log.arguments("set_history_limit") == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_rejects_too_many_arguments(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """History limit rejects commands with more than two arguments."""
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 70,
        "/history_limit 10 20 30",
    )

    assert sent_texts(session) == [
        (
            "⚠️ Слишком много аргументов.\n"
            "Пример: /history_limit 20 или /history_limit ID 100."
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 80, "/history_limit 10", "set_history_limit"),
        (HISTORY_USER_ID + 81, "/history_limit", "get_admin_ids"),
    ],
)
async def test_history_limit_propagates_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    """History limit commands propagate failures from database operations."""
    user_id, command_text, failed_operation = case
    expected_failed_operation = "get_admin_ids"
    if failed_operation == expected_failed_operation:
        access_database.scenario.fail_admin_lookup_on = 2
    else:
        access_database.scenario.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, user_id, command_text)

    assert sent_texts(dispatcher_runtime[2]) == []
