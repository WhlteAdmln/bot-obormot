# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for admin handler."""

import logging
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import (
    EditMessageText,
)
from aiogram.types import User

from bot_obormot.handlers import admin
from bot_obormot.handlers.admin import handler as admin_handler
from bot_obormot.handlers.admin.handler import cmd_ban, cmd_unban
from tests.support.dispatcher import (
    HISTORY_ADMIN_ID,
    HISTORY_USER_ID,
    SUPERVISOR_ID,
    AccessDatabase,
    FakeLLM,
    feed_command,
    sent_texts,
)
from tests.support.handler_messages import SETTINGS, FakeMessage
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
    make_update,
)


def _edited_texts(session: FakeTelegramSession) -> list[str]:
    """Extract text fields from outgoing EditMessageText requests."""
    return [
        request.text
        for request in session.requests
        if isinstance(request, EditMessageText) and request.text is not None
    ]


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
        await admin_handler.cmd_admin_add(message, command, SETTINGS, database)

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
        await admin_handler.cmd_admin_remove(message, command, SETTINGS, database)

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
        await admin_handler.cmd_admin(message, SETTINGS, database)

    assert (
        f"AUDIT action=admin_denied actor={SETTINGS.SUPERVISOR_ID - 1} "
        "target=None result=denied"
    ) in caplog.text
    assert message.answers == ["⛔ Доступ запрещён."]


@pytest.mark.asyncio
async def test_ban_command_blocks_non_admin_and_audits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Ban command blocks non admin and audits."""
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
        await admin_handler.cmd_ban(message, command, SETTINGS, database)

    assert calls == [target_id]
    assert message.answers == [f"✅ Пользователь {target_id} заблокирован."]
    assert (
        f"AUDIT action=ban actor={actor_id} target={target_id} result=blocked"
    ) in caplog.text


@pytest.mark.asyncio
async def test_ban_rejects_supervisor_and_admin_targets() -> None:
    """Ban rejects supervisor and admin targets."""
    actor_id = SETTINGS.SUPERVISOR_ID
    admin_id = 123456789

    async def get_admin_ids() -> set[object]:
        return {admin_id}

    database = SimpleNamespace(get_admin_ids=get_admin_ids)

    # Verify that a protected target never reaches the database.
    async def forbidden_block(_user_id: object) -> None:
        pytest.fail("Нельзя вызывать block_user для защищённой цели")

    database.block_user = forbidden_block

    for target_id in (actor_id, admin_id):
        message = FakeMessage(actor_id)
        await admin_handler.cmd_ban(
            message, SimpleNamespace(args=str(target_id)), SETTINGS, database
        )
        assert "заблокировать нельзя" in message.answers[0]


@pytest.mark.asyncio
async def test_unban_command_removes_block_and_audits(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unban command removes block and audits."""
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
        await admin_handler.cmd_unban(
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
    """Database admin can ban non admin."""
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
        await admin_handler.cmd_ban(
            message, SimpleNamespace(args=str(target_id)), SETTINGS, database
        )

    assert blocked == [target_id]
    assert message.answers == [f"✅ Пользователь {target_id} заблокирован."]
    assert f"AUDIT action=ban actor={actor_id}" in caplog.text


@pytest.mark.asyncio
async def test_non_admin_cannot_ban(caplog: pytest.LogCaptureFixture) -> None:
    """Non admin cannot ban."""
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
        await admin_handler.cmd_ban(
            message, SimpleNamespace(args=str(target_id)), SETTINGS, database
        )

    assert message.answers == ["⛔ Доступ запрещён."]
    assert (
        f"AUDIT action=admin_denied actor={actor_id} target=None result=denied"
    ) in caplog.text


def test_ban_commands_are_registered() -> None:
    """Ban commands are registered."""
    callbacks = {handler.callback for handler in admin.router.message.handlers}
    assert cmd_ban in callbacks
    assert cmd_unban in callbacks


@pytest.mark.asyncio
async def test_health_reports_all_component_statuses(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Health reports Telegram, database and LLM status."""
    access_database.admin_ids = {HISTORY_ADMIN_ID}

    session = await feed_command(dispatcher_runtime, HISTORY_ADMIN_ID, "/health extra")

    assert sent_texts(session) == ["🔎 Проверяю состояние компонентов..."]
    assert _edited_texts(session) == [
        (
            "🩺 <b>Состояние бота</b>\n\n"
            "🟢 Telegram API: Доступен\n"
            "🟢 База данных: Подключена\n"
            "🟢 Инференс: Доступен"
        )
    ]


@pytest.mark.asyncio
async def test_health_reports_failed_telegram_database_and_llm(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health reports failed dependencies without aborting the command."""

    async def fail_get_me(_bot: Bot) -> User:
        msg = "Telegram unavailable"
        raise RuntimeError(msg)

    dispatcher, bot, session = dispatcher_runtime
    access_database.failed_operation = "health_check"
    monkeypatch.setattr(Bot, "get_me", fail_get_me)
    dispatcher.workflow_data["llm_client"] = FakeLLM((False, "Недоступен"))

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=SUPERVISOR_ID, text="/health")),
    )

    assert sent_texts(session) == ["🔎 Проверяю состояние компонентов..."]
    assert _edited_texts(session) == [
        (
            "🩺 <b>Состояние бота</b>\n\n"
            "🔴 Telegram API: Недоступен\n"
            "🔴 База данных: Ошибка подключения\n"
            "🔴 Инференс: Недоступен"
        )
    ]


@pytest.mark.asyncio
async def test_health_denies_user_when_admin_lookup_fails(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Health reports a permission lookup failure to a non-supervisor."""
    access_database.fail_admin_lookup_on = 2

    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 100,
        "/health",
    )

    assert sent_texts(session) == ["⚠️ Не удалось проверить права администратора."]


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
    assert access_database.add_admin_calls == []
    assert access_database.remove_admin_calls == []


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
    access_database.failed_operation = operation

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
    access_database.add_admin_result = result

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_add 8001",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.add_admin_calls == [8001]


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
    assert access_database.add_admin_calls == []


@pytest.mark.asyncio
async def test_admin_add_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin add propagates database failures."""
    access_database.failed_operation = "add_admin"

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
    access_database.remove_admin_result = result

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/admin_remove 8001",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.remove_admin_calls == [8001]


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
    assert access_database.remove_admin_calls == []


@pytest.mark.asyncio
async def test_admin_remove_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Admin remove propagates database failures."""
    access_database.failed_operation = "remove_admin"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/admin_remove 8001")


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
    """Ban reports both new and existing blocks."""
    result, expected_text = case
    access_database.block_user_result = result

    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        "/ban 8001",
    )

    assert sent_texts(session) == [expected_text]
    assert access_database.block_user_calls == [8001]


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
    """Ban requires a positive integer Telegram ID."""
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/ban {arguments}".rstrip(),
    )

    assert sent_texts(session) == [
        "Укажи положительный Telegram ID. Пример: /ban 123456789"
    ]
    assert access_database.block_user_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id", [SUPERVISOR_ID, 8002])
async def test_ban_protects_supervisor_and_administrators(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    target_id: int,
) -> None:
    """Ban refuses to block the supervisor or another administrator."""
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
    assert access_database.block_user_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_operation", ["get_admin_ids", "block_user"])
async def test_ban_propagates_database_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    failed_operation: str,
) -> None:
    """Ban propagates permission lookup and block operation failures."""
    access_database.failed_operation = failed_operation

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/ban 8001")


@pytest.mark.asyncio
async def test_unban_reports_success_and_missing_blocks(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Unban reports successful and unsuccessful unblock operations."""
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
    assert sent_texts(session) == ["✅ Блокировка пользователя 8001 снята."]

    access_database.unblock_user_result = False
    session = await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8002")
    assert sent_texts(session)[-1:] == ["ℹ️ Пользователь 8002 не был заблокирован."]
    assert access_database.unblock_user_calls == [8001, 8002]


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
    """Unban requires a positive integer Telegram ID."""
    session = await feed_command(
        dispatcher_runtime,
        SUPERVISOR_ID,
        f"/unban {arguments}".rstrip(),
    )

    assert sent_texts(session) == [
        "Укажи положительный Telegram ID. Пример: /unban 123456789"
    ]
    assert access_database.unblock_user_calls == []


@pytest.mark.asyncio
async def test_unban_propagates_database_failure(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """Unban propagates database failures."""
    access_database.failed_operation = "unblock_user"

    with pytest.raises(RuntimeError, match="database unavailable"):
        await feed_command(dispatcher_runtime, SUPERVISOR_ID, "/unban 8001")
