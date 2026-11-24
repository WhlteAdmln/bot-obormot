# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the administrator management commands."""

import logging
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher

from bot_obormot.handlers.admin.handler import admins
from tests.support.dispatcher import (
    HISTORY_USER_ID,
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
async def test_admin_add_writes_audit_record(caplog: pytest.LogCaptureFixture) -> None:
    """Admin add writes audit record."""
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 123456789

    async def add_admin(user_id: int) -> bool:
        assert user_id == target_id
        return True

    database = SimpleNamespace(add_admin=add_admin)
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await admins.cmd_admin_add(message, command, SETTINGS, database)

    assert (
        f"AUDIT action=admin_add actor={actor_id} target={target_id} result=added"
    ) in caplog.text


@pytest.mark.asyncio
async def test_admin_remove_writes_not_found_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Admin remove writes not found result."""
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 123456789

    async def remove_admin(user_id: int) -> bool:
        assert user_id == target_id
        return False

    database = SimpleNamespace(remove_admin=remove_admin)
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await admins.cmd_admin_remove(message, command, SETTINGS, database)

    assert (
        f"AUDIT action=admin_remove actor={actor_id} "
        f"target={target_id} result=not_found"
    ) in caplog.text


@pytest.mark.asyncio
async def test_non_supervisor_admin_command_is_audited(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Non supervisor admin command is audited."""
    message = FakeMessage(SETTINGS.SUPERVISOR_ID - 1)
    database = SimpleNamespace()

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await admins.cmd_admin(message, SETTINGS, database)

    assert (
        f"AUDIT action=admin_denied actor={SETTINGS.SUPERVISOR_ID - 1} "
        "target=None result=denied"
    ) in caplog.text
    assert message.answers == ["⛔ Доступ запрещён."]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_text",
    ["/admin", "/admins", "/admin_add 123", "/admin_remove 123"],
)
async def test_supervisor_commands_deny_non_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
) -> None:
    """Supervisor-only commands reject ordinary users."""
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 101,
        command_text,
    )

    assert sent_texts(session) == ["⛔ Доступ запрещён."]
    assert access_database.log.arguments("add_admin") == []
    assert access_database.log.arguments("remove_admin") == []


@pytest.mark.asyncio
async def test_admin_panel_reports_database_counts(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin panel displays administrator and allowlist counts."""
    access_database.admin_ids = {8003, 8001, 8002}

    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin extra")

    assert sent_texts(session) == [
        (
            "🛠 Панель управления\n\n"
            f"👑 Supervisor ID: {SUPERVISOR_ID}\n"
            "👥 Обычных администраторов: 3\n"
            "🔐 Пользователей в allowlist: 0\n\n"
            "Команды управления:\n"
            "/admins — список администраторов\n"
            "/admin_add ID — добавить администратора\n"
            "/admin_remove ID — удалить администратора"
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("admin_ids", "expected_text"),
    [
        (
            {8003, 8001, 8002},
            (
                f"👥 Список администраторов\n\n👑 Supervisor: {SUPERVISOR_ID}\n"
                "\nОбычные администраторы:\n• 8001\n• 8002\n• 8003"
            ),
        ),
        (
            set(),
            (
                f"👥 Список администраторов\n\n👑 Supervisor: {SUPERVISOR_ID}\n"
                "\nОбычных администраторов пока нет."
            ),
        ),
    ],
)
async def test_admins_lists_sorted_ids_or_empty_state(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    admin_ids: set[int],
    expected_text: str,
) -> None:
    """Admins lists sorted IDs and handles an empty administrator list."""
    access_database.admin_ids = admin_ids

    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admins")

    assert sent_texts(session) == [expected_text]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_text", "operation"),
    [("/admin", "get_admin_ids"), ("/admins", "get_admin_ids")],
)
async def test_admin_read_commands_propagate_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
    operation: str,
) -> None:
    """Admin panel and list propagate database lookup failures."""
    access_database.scenario.failed_operation = operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, command_text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (True, "✅ Пользователь 8001 добавлен в список администраторов."),
        (False, "ℹ️ Пользователь 8001 уже является администратором."),
    ],
)
async def test_admin_add_reports_added_and_existing_users(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, str],
) -> None:
    """Admin add reports both newly added and existing administrators."""
    result, expected_text = case
    access_database.scenario.results["add_admin"] = result

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_add 8001",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.log.arguments("add_admin") == [(8001,)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "expected_text"),
    [
        ("", "Укажи Telegram ID пользователя.\nПример: /admin_add 123456789"),
        ("invalid", "⛔ Telegram ID должен быть целым числом."),
        ("0", "⛔ Telegram ID должен быть положительным числом."),
        (
            str(SUPERVISOR_ID),
            "ℹ️ Этот пользователь уже является Supervisor.",
        ),
    ],
)
async def test_admin_add_rejects_invalid_arguments_and_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
    expected_text: str,
) -> None:
    """Admin add validates IDs and protects the supervisor."""
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_add {arguments}".rstrip(),
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.log.arguments("add_admin") == []


@pytest.mark.asyncio
async def test_admin_add_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin add propagates database failures."""
    access_database.scenario.failed_operation = "add_admin"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin_add 8001")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (True, "✅ Пользователь 8001 удалён из списка администраторов."),
        (False, "ℹ️ Пользователь 8001 не найден среди администраторов."),
    ],
)
async def test_admin_remove_reports_removed_and_missing_users(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, str],
) -> None:
    """Admin remove reports successful and unsuccessful removals."""
    result, expected_text = case
    access_database.scenario.results["remove_admin"] = result

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_remove 8001",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.log.arguments("remove_admin") == [(8001,)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("arguments", "expected_text"),
    [
        ("", "Укажи Telegram ID пользователя.\nПример: /admin_remove 123456789"),
        ("invalid", "⛔ Telegram ID должен быть целым числом."),
        ("0", "⛔ Telegram ID должен быть положительным числом."),
        (str(SUPERVISOR_ID), "⛔ Нельзя удалить Supervisor."),
    ],
)
async def test_admin_remove_rejects_invalid_arguments_and_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
    expected_text: str,
) -> None:
    """Admin remove validates IDs and protects the supervisor."""
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_remove {arguments}".rstrip(),
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.log.arguments("remove_admin") == []


@pytest.mark.asyncio
async def test_admin_remove_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin remove propagates database failures."""
    access_database.scenario.failed_operation = "remove_admin"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin_remove 8001")
