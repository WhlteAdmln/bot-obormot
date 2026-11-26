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


async def _set_limit_for_another_user(
    monkeypatch: pytest.MonkeyPatch, target_id: int, exchange_limit: int
) -> list[tuple[int, int | None]]:
    calls: list[tuple[int, int | None]] = []

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
    message = FakeMessage(AUDIT_SETTINGS.SUPERVISOR_ID)
    command = SimpleNamespace(args=f"{target_id} {exchange_limit}")

    await history_limits_handler.cmd_history_limit(
        message, SimpleNamespace(), command, AUDIT_SETTINGS, database
    )
    return calls


@pytest.mark.asyncio
async def test_history_limit_for_another_user_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target_id = 123456789
    exchange_limit = 35

    calls = await _set_limit_for_another_user(monkeypatch, target_id, exchange_limit)

    expected_calls = [(target_id, exchange_limit)]
    assert calls == expected_calls, "the target limit was not stored"


@pytest.mark.asyncio
async def test_history_limit_for_another_user_is_audited(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = AUDIT_SETTINGS.SUPERVISOR_ID
    target_id = 987650001
    exchange_limit = 17

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await _set_limit_for_another_user(monkeypatch, target_id, exchange_limit)

    expected_record = (
        f"AUDIT action=history_limit_set actor={actor_id} "
        f"target={target_id} result={exchange_limit}"
    )
    assert expected_record in caplog.text, "the target limit change was not audited"


@pytest.mark.asyncio
async def test_history_limit_command_ignores_messages_without_sender() -> None:
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
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 30,
        "/history_limit",
    )

    expected_texts = [
        (
            "Использование:\n"
            "/history — показать текущий лимит\n"
            "/history_limit 20 — установить свой лимит\n"
            "/history_limit ID 100 — установить лимит другому пользователю "
            "(только администратор)."
        )
    ]
    assert sent_texts(session) == expected_texts, "the usage text differs"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 31, set(), 12),
        (HISTORY_ADMIN_ID, {HISTORY_ADMIN_ID}, SETTINGS.MAX_HISTORY_EXCHANGES),
        (SUPERVISOR_ID, set(), SETTINGS.MAX_HISTORY_EXCHANGES),
    ],
)
async def test_history_limit_confirms_own_limit_for_user_admin_and_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], int],
) -> None:
    user_id, admin_ids, limit = case
    access_database.admin_ids = admin_ids

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {limit}",
    )

    expected_texts = [f"✅ Твой лимит истории установлен: {limit} полных обменов."]
    assert sent_texts(session) == expected_texts, "the own limit was not confirmed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 32, set(), 7),
        (HISTORY_ADMIN_ID, {HISTORY_ADMIN_ID}, SETTINGS.MAX_HISTORY_EXCHANGES - 3),
        (SUPERVISOR_ID, set(), SETTINGS.MAX_HISTORY_EXCHANGES),
    ],
)
async def test_history_limit_sets_own_limit_for_user_admin_and_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], int],
) -> None:
    user_id, admin_ids, limit = case
    access_database.admin_ids = admin_ids

    await feed_command(dispatcher_runtime, user_id, f"/history_limit {limit}")

    expected_calls = [(user_id, limit)]
    stored = access_database.log.arguments("set_history_limit")
    assert stored == expected_calls, "the own limit was not stored"


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
@pytest.mark.usefixtures("access_database")
async def test_history_limit_rejects_invalid_own_limits(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    user_id, raw_limit, expected_text = case

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {raw_limit}",
    )

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the invalid limit was not rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_USER_ID + 43, "много"),
        (HISTORY_USER_ID + 44, "0"),
        (HISTORY_USER_ID + 45, str(SETTINGS.DEFAULT_HISTORY_EXCHANGES + 9)),
    ],
)
async def test_history_limit_keeps_invalid_own_limits_unsaved(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    user_id, raw_limit = case

    await feed_command(dispatcher_runtime, user_id, f"/history_limit {raw_limit}")

    expected_empty: list[tuple[object, ...]] = []
    stored = access_database.log.arguments("set_history_limit")
    assert stored == expected_empty, "an invalid own limit was stored"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_denies_non_admin_target_changes(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    target_id = 444000002
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 50,
        f"/history_limit {target_id} 10",
    )

    expected_texts = [
        "⛔ Назначать лимиты другим пользователям могут только администраторы."
    ]
    assert sent_texts(session) == expected_texts, "a non-admin changed a target limit"


@pytest.mark.asyncio
async def test_history_limit_confirms_admin_target_limit(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = HISTORY_ADMIN_ID + 1
    target_id = 444000002
    limit = 25
    access_database.admin_ids = {user_id}

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {target_id} {limit}",
    )

    expected_texts = [
        f"✅ Для пользователя {target_id} установлен лимит {limit} полных обменов."
    ]
    assert sent_texts(session) == expected_texts, "the target limit was not confirmed"


@pytest.mark.asyncio
async def test_history_limit_allows_admin_to_change_target_limit(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    user_id = HISTORY_ADMIN_ID + 6
    target_id = 444000777
    limit = 9
    access_database.admin_ids = {user_id}

    await feed_command(
        dispatcher_runtime, user_id, f"/history_limit {target_id} {limit}"
    )

    expected_calls = [(target_id, limit)]
    stored = access_database.log.arguments("set_history_limit")
    assert stored == expected_calls, "the target limit was not stored"


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
            "444000002 invalid",
            "⚠️ Укажи корректный ID пользователя и целое число лимита.",
        ),
        (
            HISTORY_ADMIN_ID + 5,
            "444000002 0",
            f"⚠️ Допустимый лимит: от 1 до {SETTINGS.MAX_HISTORY_EXCHANGES}.",
        ),
    ],
)
async def test_history_limit_rejects_invalid_target_arguments(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str, str],
) -> None:
    user_id, arguments, expected_text = case
    access_database.admin_ids = {user_id}

    session = await feed_command(
        dispatcher_runtime,
        user_id,
        f"/history_limit {arguments}",
    )

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "invalid target was not rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (HISTORY_ADMIN_ID + 7, "кто-то 10"),
        (HISTORY_ADMIN_ID + 8, "0 15"),
        (HISTORY_ADMIN_ID + 9, "444000003 много"),
        (HISTORY_ADMIN_ID + 10, "444000004 0"),
    ],
)
async def test_history_limit_keeps_invalid_target_limits_unsaved(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    user_id, arguments = case
    access_database.admin_ids = {user_id}

    await feed_command(dispatcher_runtime, user_id, f"/history_limit {arguments}")

    expected_empty: list[tuple[object, ...]] = []
    stored = access_database.log.arguments("set_history_limit")
    assert stored == expected_empty, "an invalid target limit was stored"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_history_limit_rejects_too_many_arguments(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 70,
        "/history_limit 10 20 30",
    )

    expected_texts = [
        (
            "⚠️ Слишком много аргументов.\n"
            "Пример: /history_limit 20 или /history_limit ID 100."
        )
    ]
    assert sent_texts(session) == expected_texts, "too many arguments were accepted"


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
    user_id, command_text, failed_operation = case
    expected_failed_operation = "get_admin_ids"
    if failed_operation == expected_failed_operation:
        access_database.scenario.fail_admin_lookup_on = 2
    else:
        access_database.scenario.failed_operation = failed_operation

    session = dispatcher_runtime[2]
    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, user_id, command_text)

    expected_empty: list[str] = []
    assert sent_texts(session) == expected_empty, "a reply was sent after a failure"
