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
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 123456789
    database = AccessDatabase()
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await admins.cmd_admin_add(message, command, SETTINGS, database)

    expected_record = (
        f"AUDIT action=admin_add actor={actor_id} target={target_id} result=added"
    )
    assert expected_record in caplog.text, "the added administrator was not audited"


@pytest.mark.asyncio
async def test_admin_add_passes_the_target_to_the_database() -> None:
    target_id = 734120956
    database = AccessDatabase()
    message = FakeMessage(SETTINGS.SUPERVISOR_ID)
    command = SimpleNamespace(args=str(target_id))

    await admins.cmd_admin_add(message, command, SETTINGS, database)

    expected_arguments = [(target_id,)]
    actual_arguments = database.log.arguments("add_admin")
    assert actual_arguments == expected_arguments, "add_admin got another user"


@pytest.mark.asyncio
async def test_admin_remove_writes_not_found_result(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID
    target_id = 123456789
    database = AccessDatabase()
    database.scenario.results["remove_admin"] = False
    message = FakeMessage(actor_id)
    command = SimpleNamespace(args=str(target_id))

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await admins.cmd_admin_remove(message, command, SETTINGS, database)

    expected_record = (
        f"AUDIT action=admin_remove actor={actor_id} "
        f"target={target_id} result=not_found"
    )
    assert expected_record in caplog.text, "the missing administrator was not audited"


@pytest.mark.asyncio
async def test_admin_remove_passes_the_target_to_the_database() -> None:
    target_id = 560089123
    database = AccessDatabase()
    database.scenario.results["remove_admin"] = False
    message = FakeMessage(SETTINGS.SUPERVISOR_ID)
    command = SimpleNamespace(args=str(target_id))

    await admins.cmd_admin_remove(message, command, SETTINGS, database)

    expected_arguments = [(target_id,)]
    actual_arguments = database.log.arguments("remove_admin")
    assert actual_arguments == expected_arguments, "remove_admin got another user"


@pytest.mark.asyncio
async def test_non_supervisor_admin_command_is_audited(
    caplog: pytest.LogCaptureFixture,
) -> None:
    actor_id = SETTINGS.SUPERVISOR_ID - 1
    message = FakeMessage(actor_id)
    database = SimpleNamespace()

    with caplog.at_level(logging.INFO, logger="bot_obormot.audit"):
        await admins.cmd_admin(message, SETTINGS, database)

    expected_record = (
        f"AUDIT action=admin_denied actor={actor_id} target=None result=denied"
    )
    assert expected_record in caplog.text, "the denied command was not audited"


@pytest.mark.asyncio
async def test_non_supervisor_admin_command_is_answered_with_a_denial() -> None:
    message = FakeMessage(SETTINGS.SUPERVISOR_ID - 17)
    database = SimpleNamespace()

    await admins.cmd_admin(message, SETTINGS, database)

    expected_answers = ["⛔ Доступ запрещён."]
    assert message.answers == expected_answers, "the denial answer differs"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_text",
    ["/admin", "/admins", "/admin_add 123", "/admin_remove 123"],
)
async def test_supervisor_commands_deny_non_supervisor(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 101,
        command_text,
    )

    expected_texts = ["⛔ Доступ запрещён."]
    assert sent_texts(session) == expected_texts, "a non-supervisor was not denied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_text",
    ["/admin", "/admins", "/admin_add 123", "/admin_remove 123"],
)
async def test_supervisor_commands_from_non_supervisor_add_no_admin(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
) -> None:
    await feed_command(dispatcher_runtime, HISTORY_USER_ID + 202, command_text)

    expected_empty: list[tuple[int, ...]] = []
    actual_arguments = access_database.log.arguments("add_admin")
    assert actual_arguments == expected_empty, "a non-supervisor added an admin"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_text",
    ["/admin", "/admins", "/admin_add 123", "/admin_remove 123"],
)
async def test_supervisor_commands_from_non_supervisor_remove_no_admin(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
) -> None:
    await feed_command(dispatcher_runtime, HISTORY_USER_ID + 303, command_text)

    expected_empty: list[tuple[int, ...]] = []
    actual_arguments = access_database.log.arguments("remove_admin")
    assert actual_arguments == expected_empty, "a non-supervisor removed an admin"


@pytest.mark.asyncio
async def test_admin_panel_reports_database_counts(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.admin_ids = {8003, 8001, 8002}

    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin extra")

    expected_texts = [
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
    assert sent_texts(session) == expected_texts, "the admin panel text differs"


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
    access_database.admin_ids = admin_ids

    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admins")

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the administrator list differs"


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
    access_database.scenario.failed_operation = operation

    with pytest.raises(RuntimeError) as excinfo:
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, command_text)

    expected_text = "database unavailable"
    assert expected_text in str(excinfo.value), "the database failure was replaced"


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
    result, expected_text = case
    access_database.scenario.results["add_admin"] = result

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_add 8001",
    )

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the add answer differs"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [(True, 8001), (False, 8024)])
async def test_admin_add_command_passes_the_parsed_id_to_the_database(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, int],
) -> None:
    result, user_id = case
    access_database.scenario.results["add_admin"] = result

    await feed_command(dispatcher_runtime, SUPERVISOR_ID, f"/admin_add {user_id}")

    expected_arguments = [(user_id,)]
    actual_arguments = access_database.log.arguments("add_admin")
    assert actual_arguments == expected_arguments, "add_admin got another user"


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
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
    expected_text: str,
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_add {arguments}".rstrip(),
    )

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the rejection answer differs"


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["", "invalid", "0", str(SUPERVISOR_ID)])
async def test_admin_add_with_rejected_arguments_adds_no_admin(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_add {arguments}".rstrip(),
    )

    expected_empty: list[tuple[int, ...]] = []
    actual_arguments = access_database.log.arguments("add_admin")
    assert actual_arguments == expected_empty, "a rejected argument added an admin"


@pytest.mark.asyncio
async def test_admin_add_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.scenario.failed_operation = "add_admin"

    with pytest.raises(RuntimeError) as excinfo:
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin_add 8001")

    expected_text = "database unavailable"
    assert expected_text in str(excinfo.value), "the database failure was replaced"


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
    result, expected_text = case
    access_database.scenario.results["remove_admin"] = result

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_remove 8001",
    )

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the remove answer differs"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", [(True, 8001), (False, 8024)])
async def test_admin_remove_command_passes_the_parsed_id_to_the_database(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[bool, int],
) -> None:
    result, user_id = case
    access_database.scenario.results["remove_admin"] = result

    await feed_command(dispatcher_runtime, SUPERVISOR_ID, f"/admin_remove {user_id}")

    expected_arguments = [(user_id,)]
    actual_arguments = access_database.log.arguments("remove_admin")
    assert actual_arguments == expected_arguments, "remove_admin got another user"


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
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
    expected_text: str,
) -> None:
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_remove {arguments}".rstrip(),
    )

    expected_texts = [expected_text]
    assert sent_texts(session) == expected_texts, "the rejection answer differs"


@pytest.mark.asyncio
@pytest.mark.parametrize("arguments", ["", "invalid", "0", str(SUPERVISOR_ID)])
async def test_admin_remove_with_rejected_arguments_removes_no_admin(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    arguments: str,
) -> None:
    await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/admin_remove {arguments}".rstrip(),
    )

    expected_empty: list[tuple[int, ...]] = []
    actual_arguments = access_database.log.arguments("remove_admin")
    assert actual_arguments == expected_empty, "a rejected argument removed an admin"


@pytest.mark.asyncio
async def test_admin_remove_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.scenario.failed_operation = "remove_admin"

    with pytest.raises(RuntimeError) as excinfo:
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin_remove 8001")

    expected_text = "database unavailable"
    assert expected_text in str(excinfo.value), "the database failure was replaced"
