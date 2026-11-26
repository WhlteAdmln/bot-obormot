# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the ban and unban commands."""

import logging
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher

from bot_obormot.handlers.admin.handler import bans
from tests.support.dispatcher import (
    SUPERVISOR_ID,
    AccessDatabase,
    feed_command,
    sent_texts,
)
from tests.support.handler_messages import SETTINGS, FakeMessage
from tests.support.telegram import (
    FakeTelegramSession,
)


async def _ban(actor_id: int, target_id: int, database: AccessDatabase) -> FakeMessage:
    """Call the ban handler directly and return the message it answered."""
    message = FakeMessage(actor_id)
    await bans.cmd_ban(
        message, SimpleNamespace(args=str(target_id)), SETTINGS, database
    )
    return message


async def _unban(
    actor_id: int, target_id: int, database: AccessDatabase
) -> FakeMessage:
    """Call the unban handler directly and return the message it answered."""
    message = FakeMessage(actor_id)
    await bans.cmd_unban(
        message, SimpleNamespace(args=str(target_id)), SETTINGS, database
    )
    return message


@pytest.mark.asyncio
async def test_ban_command_blocks_a_non_admin_target() -> None:
    target_id = 123456789
    database = AccessDatabase()
    await _ban(SETTINGS.SUPERVISOR_ID, target_id, database)
    expected_calls = [(target_id,)]
    blocked = database.log.arguments("block_user")
    assert blocked == expected_calls, "the target was not blocked"


@pytest.mark.asyncio
async def test_ban_command_confirms_the_block() -> None:
    target_id = 314159
    message = await _ban(SETTINGS.SUPERVISOR_ID, target_id, AccessDatabase())
    expected_answers = [f"✅ Пользователь {target_id} заблокирован."]
    assert message.answers == expected_answers, "the block was not confirmed"


@pytest.mark.asyncio
async def test_ban_command_audits_the_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 271828182
    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await _ban(actor_id, target_id, AccessDatabase())
    expected_line = (
        f"AUDIT action=ban actor={actor_id} target={target_id} result=blocked"
    )
    assert expected_line in caplog.text, "the block was not audited"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id", [SETTINGS.SUPERVISOR_ID, 123456789])
async def test_ban_refuses_supervisor_and_admin_targets(target_id: int) -> None:
    database = AccessDatabase(admin_ids={123456789})
    message = await _ban(SETTINGS.SUPERVISOR_ID, target_id, database)
    refusal_text = "заблокировать нельзя"
    assert refusal_text in message.answers[0], "a protected target was not refused"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id", [SETTINGS.SUPERVISOR_ID, 55443322])
async def test_ban_does_not_block_supervisor_and_admin_targets(
    target_id: int,
) -> None:
    database = AccessDatabase(admin_ids={55443322})
    await _ban(SETTINGS.SUPERVISOR_ID, target_id, database)
    expected_empty: list[tuple[int, ...]] = []
    blocked = database.log.arguments("block_user")
    assert blocked == expected_empty, "a protected target was blocked"


@pytest.mark.asyncio
async def test_unban_command_unblocks_the_target() -> None:
    target_id = 123456789
    database = AccessDatabase()
    await _unban(SETTINGS.SUPERVISOR_ID, target_id, database)
    expected_calls = [(target_id,)]
    unblocked = database.log.arguments("unblock_user")
    assert unblocked == expected_calls, "the target was not unblocked"


@pytest.mark.asyncio
async def test_unban_command_confirms_the_unblock() -> None:
    target_id = 86420
    message = await _unban(SETTINGS.SUPERVISOR_ID, target_id, AccessDatabase())
    expected_answers = [f"✅ Блокировка пользователя {target_id} снята."]
    assert message.answers == expected_answers, "the unblock was not confirmed"


@pytest.mark.asyncio
async def test_unban_command_audits_the_unblock(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 97531
    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await _unban(actor_id, target_id, AccessDatabase())
    expected_line = (
        f"AUDIT action=unban actor={actor_id} target={target_id} result=unblocked"
    )
    assert expected_line in caplog.text, "the unblock was not audited"


@pytest.mark.asyncio
async def test_database_admin_can_ban_non_admin() -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 10
    target_id = 123456789
    database = AccessDatabase(admin_ids={actor_id})
    await _ban(actor_id, target_id, database)
    expected_calls = [(target_id,)]
    blocked = database.log.arguments("block_user")
    assert blocked == expected_calls, "a database admin could not block a user"


@pytest.mark.asyncio
async def test_database_admin_ban_is_confirmed() -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 17
    target_id = 60606060
    message = await _ban(actor_id, target_id, AccessDatabase(admin_ids={actor_id}))
    expected_answers = [f"✅ Пользователь {target_id} заблокирован."]
    assert message.answers == expected_answers, "the admin block was not confirmed"


@pytest.mark.asyncio
async def test_database_admin_ban_is_audited(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 23
    target_id = 70707070
    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await _ban(actor_id, target_id, AccessDatabase(admin_ids={actor_id}))
    expected_line = f"AUDIT action=ban actor={actor_id}"
    assert expected_line in caplog.text, "the admin block was not audited"


@pytest.mark.asyncio
async def test_non_admin_cannot_ban() -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 10
    message = await _ban(actor_id, 123456789, AccessDatabase())
    expected_answers = ["⛔ Доступ запрещён."]
    assert message.answers == expected_answers, "a non-admin was not refused"


@pytest.mark.asyncio
async def test_non_admin_ban_blocks_nobody() -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 31
    database = AccessDatabase()
    await _ban(actor_id, 80808080, database)
    expected_empty: list[tuple[int, ...]] = []
    blocked = database.log.arguments("block_user")
    assert blocked == expected_empty, "a non-admin blocked a user"


@pytest.mark.asyncio
async def test_non_admin_ban_is_audited_as_denied(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 44
    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await _ban(actor_id, 90909090, AccessDatabase())
    expected_line = (
        f"AUDIT action=admin_denied actor={actor_id} target=None result=denied"
    )
    assert expected_line in caplog.text, "the denied ban was not audited"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (True, "✅ Пользователь 8001 заблокирован."),
        (False, "ℹ️ Пользователь 8001 уже заблокирован."),
    ],
)
async def test_ban_reports_blocked_and_already_blocked_users(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, str],
) -> None:
    result, expected_text = case
    access_database.scenario.results["block_user"] = result
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/ban 8001")
    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the ban reply differs"


@pytest.mark.asyncio
@pytest.mark.parametrize("results", [{"block_user": True}, {"block_user": False}])
async def test_ban_calls_block_user_once_for_the_target(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    results: dict[str, bool],
) -> None:
    access_database.scenario.results.update(results)
    await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/ban 8001")
    expected_calls = [(8001,)]
    blocked = access_database.log.arguments("block_user")
    assert blocked == expected_calls, "block_user was not called for the target"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_ban_rejects_invalid_target_ids(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/ban {arguments}".rstrip(),
    )
    expected_texts = ["Укажи положительный Telegram ID. Пример: /ban 123456789"]
    assert sent_texts(session) == expected_texts, "an invalid ID was not rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_ban_blocks_nobody_for_invalid_target_ids(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    await feed_command(dispatcher_runtime, SUPERVISOR_ID, f"/ban {arguments}".rstrip())
    expected_empty: list[tuple[int, ...]] = []
    blocked = access_database.log.arguments("block_user")
    assert blocked == expected_empty, "an invalid ID reached block_user"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id", [SUPERVISOR_ID, 8002])
async def test_ban_protects_supervisor_and_administrators(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    target_id: int,
) -> None:
    access_database.admin_ids = {8002}
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, f"/ban {target_id}")
    expected_texts = [
        (
            "⛔ Этого пользователя заблокировать нельзя. "
            "Сначала сними права администратора."
        )
    ]
    assert sent_texts(session) == expected_texts, "a protected target was not refused"


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id", [SUPERVISOR_ID, 8003])
async def test_ban_blocks_neither_supervisor_nor_administrators(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    target_id: int,
) -> None:
    access_database.admin_ids = {8003}
    await feed_command(dispatcher_runtime, SUPERVISOR_ID, f"/ban {target_id}")
    expected_empty: list[tuple[int, ...]] = []
    blocked = access_database.log.arguments("block_user")
    assert blocked == expected_empty, "a protected target was blocked"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_operation", ["get_admin_ids", "block_user"])
async def test_ban_propagates_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    failed_operation: str,
) -> None:
    access_database.scenario.failed_operation = failed_operation
    with pytest.raises(RuntimeError) as excinfo:
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/ban 8001")
    expected_text = "database unavailable"
    assert expected_text in str(excinfo.value), "the database failure was lost"


@pytest.mark.asyncio
async def test_unban_reports_success(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
    expected_texts = ["✅ Блокировка пользователя 8001 снята."]
    assert sent_texts(session) == expected_texts, "the unblock was not confirmed"


@pytest.mark.asyncio
async def test_unban_reports_missing_block(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.scenario.results["unblock_user"] = False
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8002")
    expected_texts = ["ℹ️ Пользователь 8002 не был заблокирован."]
    assert sent_texts(session) == expected_texts, "a missing block was not reported"


@pytest.mark.asyncio
async def test_unban_calls_unblock_user_for_each_target(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
    access_database.scenario.results["unblock_user"] = False
    await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8002")
    expected_calls = [(8001,), (8002,)]
    unblocked = access_database.log.arguments("unblock_user")
    assert unblocked == expected_calls, "unblock_user calls differ"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_unban_rejects_invalid_target_ids(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/unban {arguments}".rstrip(),
    )
    expected_texts = ["Укажи положительный Telegram ID. Пример: /unban 123456789"]
    assert sent_texts(session) == expected_texts, "an invalid ID was not rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_unban_unblocks_nobody_for_invalid_target_ids(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    await feed_command(
        dispatcher_runtime, SUPERVISOR_ID, f"/unban {arguments}".rstrip()
    )
    expected_empty: list[tuple[int, ...]] = []
    unblocked = access_database.log.arguments("unblock_user")
    assert unblocked == expected_empty, "an invalid ID reached unblock_user"


@pytest.mark.asyncio
async def test_unban_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.scenario.failed_operation = "unblock_user"
    with pytest.raises(RuntimeError) as excinfo:
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
    expected_text = "database unavailable"
    assert expected_text in str(excinfo.value), "the database failure was lost"
