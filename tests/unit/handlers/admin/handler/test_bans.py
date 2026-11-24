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


@pytest.mark.asyncio
async def test_ban_command_blocks_non_admin_and_audits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 123456789
    calls = []

    async def get_admin_ids() -> set[int]:
        return set()

    async def block_user(user_id: int) -> bool:
        calls.append(user_id)
        return True

    database = SimpleNamespace(get_admin_ids=get_admin_ids, block_user=block_user)
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await bans.cmd_ban(message, command, SETTINGS, database)

    assert calls == [target_id]
    assert message.answers == [f"✅ Пользователь {target_id} заблокирован."]
    assert (
        f"AUDIT action=ban actor={actor_id} target={target_id} result=blocked"
    ) in caplog.text


@pytest.mark.asyncio
async def test_ban_rejects_supervisor_and_admin_targets() -> None:
    actor_id = SETTINGS.SUPERVISOR_ID
    admin_id = 123456789

    async def get_admin_ids() -> set[object]:
        return {admin_id}

    database = SimpleNamespace(get_admin_ids=get_admin_ids)

    async def forbidden_block(_user_id: object) -> None:
        pytest.fail("Нельзя вызывать block_user для защищённой цели")

    database.block_user = forbidden_block

    for target_id in (actor_id, admin_id):
        message = FakeMessage(actor_id)
        await bans.cmd_ban(
            message, SimpleNamespace(args=str(target_id)), SETTINGS, database
        )
        refusal_text = "заблокировать нельзя"
        assert refusal_text in message.answers[0]


@pytest.mark.asyncio
async def test_unban_command_removes_block_and_audits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 123456789

    async def get_admin_ids() -> set[int]:
        return set()

    async def unblock_user(user_id: int) -> bool:
        assert user_id == target_id
        return True

    database = SimpleNamespace(get_admin_ids=get_admin_ids, unblock_user=unblock_user)
    message = FakeMessage(actor_id)

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await bans.cmd_unban(
            message, SimpleNamespace(args=str(target_id)), SETTINGS, database
        )

    assert message.answers == [f"✅ Блокировка пользователя {target_id} снята."]
    assert (
        f"AUDIT action=unban actor={actor_id} target={target_id} result=unblocked"
    ) in caplog.text


@pytest.mark.asyncio
async def test_database_admin_can_ban_non_admin(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 10
    target_id = 123456789
    blocked = []

    async def get_admin_ids() -> set[object]:
        return {actor_id}

    async def block_user(user_id: int) -> bool:
        blocked.append(user_id)
        return True

    database = SimpleNamespace(get_admin_ids=get_admin_ids, block_user=block_user)
    message = FakeMessage(actor_id)

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await bans.cmd_ban(
            message, SimpleNamespace(args=str(target_id)), SETTINGS, database
        )

    assert blocked == [target_id]
    assert message.answers == [f"✅ Пользователь {target_id} заблокирован."]
    assert f"AUDIT action=ban actor={actor_id}" in caplog.text


@pytest.mark.asyncio
async def test_non_admin_cannot_ban(caplog: pytest.LogCaptureFixture) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 10
    target_id = 123456789

    async def get_admin_ids() -> set[int]:
        return set()

    async def forbidden_block_user(_user_id: object) -> None:
        pytest.fail("Пользователь без прав не должен блокировать аккаунты")

    database = SimpleNamespace(
        get_admin_ids=get_admin_ids, block_user=forbidden_block_user
    )
    message = FakeMessage(actor_id)

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await bans.cmd_ban(
            message, SimpleNamespace(args=str(target_id)), SETTINGS, database
        )

    assert message.answers == ["⛔ Доступ запрещён."]
    assert (
        f"AUDIT action=admin_denied actor={actor_id} target=None result=denied"
    ) in caplog.text


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

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/ban 8001",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.log.arguments("block_user") == [(8001,)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_ban_rejects_invalid_target_ids(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/ban {arguments}".rstrip(),
    )

    assert sent_texts(session) == [
        "Укажи положительный Telegram ID. Пример: /ban 123456789"
    ]
    assert access_database.log.arguments("block_user") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id", [SUPERVISOR_ID, 8002])
async def test_ban_protects_supervisor_and_administrators(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    target_id: int,
) -> None:
    access_database.admin_ids = {8002}

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/ban {target_id}",
    )

    assert sent_texts(session) == [
        (
            "⛔ Этого пользователя заблокировать нельзя. "
            "Сначала сними права администратора."
        )
    ]
    assert access_database.log.arguments("block_user") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_operation", ["get_admin_ids", "block_user"])
async def test_ban_propagates_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    failed_operation: str,
) -> None:
    access_database.scenario.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/ban 8001")


@pytest.mark.asyncio
async def test_unban_reports_success_and_missing_blocks(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
    assert sent_texts(session) == ["✅ Блокировка пользователя 8001 снята."]

    access_database.scenario.results["unblock_user"] = False
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8002")
    assert sent_texts(session)[-1:] == ["ℹ️ Пользователь 8002 не был заблокирован."]
    assert access_database.log.arguments("unblock_user") == [(8001,), (8002,)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "arguments",
    ["", "invalid", "0", "-1"],
)
async def test_unban_rejects_invalid_target_ids(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/unban {arguments}".rstrip(),
    )

    assert sent_texts(session) == [
        "Укажи положительный Telegram ID. Пример: /unban 123456789"
    ]
    assert access_database.log.arguments("unblock_user") == []


@pytest.mark.asyncio
async def test_unban_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.scenario.failed_operation = "unblock_user"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
