# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for start handler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import (
    SetMyCommands,
)

from bot_obormot.handlers.start.handler import cmd_start
from bot_obormot.services.database import Database
from tests.support.dispatcher import (
    ADMIN_ID,
    SUPERVISOR_ID,
    USER_ID,
    AccessDatabase,
    sent_texts,
)
from tests.support.settings import make_settings
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
    make_update,
)


class _FailingAdminDatabase:
    """Simulate an administrator lookup failure in the start handler."""

    def __init__(self) -> None:
        self.admin_lookup_calls = 0

    async def get_blocked_ids(self) -> set[int]:
        """Return no blocked users for the access middleware."""
        return set()

    async def get_admin_ids(self) -> set[int]:
        """Raise an error when administrator IDs are requested."""
        self.admin_lookup_calls += 1
        if self.admin_lookup_calls == 1:
            return set()
        msg = "database unavailable"
        raise RuntimeError(msg)


def _sent_command_names(session: FakeTelegramSession) -> set[str]:
    """Extract command names from the outgoing SetMyCommands request."""
    requests = [
        request for request in session.requests if isinstance(request, SetMyCommands)
    ]
    assert len(requests) == 1
    return {command.command for command in requests[0].commands}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID, set(), False, False, "/start"),
        (ADMIN_ID, {ADMIN_ID}, True, False, "/start"),
        (SUPERVISOR_ID, set(), True, True, "/start"),
        (USER_ID + 1, set(), False, False, "/start extra arguments"),
    ],
)
async def test_start_routes_users_and_builds_their_command_menu(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], bool, bool, str],
) -> None:
    """Start sends the appropriate help and command menu for each role."""
    user_id, admin_ids, expected_admin, expected_supervisor, command_text = case
    dispatcher, bot, session = dispatcher_runtime
    access_database.admin_ids = admin_ids

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    command_names = _sent_command_names(session)
    texts = sent_texts(session)

    assert len(texts) == 1
    assert "Привет! 👋 Я бот для работы с LLM в формате чата." in texts[0]
    assert "/forget_me — удалить все свои данные" in texts[0]
    assert ("health" in command_names) is expected_admin
    assert ({"ban", "unban"} <= command_names) is expected_admin
    assert ("🩺 Состояние бота:" in texts[0]) is expected_admin
    assert ({"admin", "admins", "admin_add", "admin_remove"} <= command_names) is (
        expected_supervisor
    )
    assert ("🛠 Управление администраторами:" in texts[0]) is expected_supervisor


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_start_falls_back_to_regular_menu_when_database_fails(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    """A failed administrator lookup does not prevent the welcome response."""
    dispatcher, bot, session = dispatcher_runtime
    dispatcher.workflow_data["database"] = _FailingAdminDatabase()

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=USER_ID + 2, text="/start")),
    )

    command_names = _sent_command_names(session)
    texts = sent_texts(session)

    assert len(texts) == 1
    assert "Привет! 👋 Я бот для работы с LLM в формате чата." in texts[0]
    assert "health" not in command_names
    assert "🩺 Состояние бота:" not in texts[0]
    assert "admin" not in command_names
    assert "🛠 Управление администраторами:" not in texts[0]


@pytest.mark.asyncio
async def test_start_help_and_command_menu_include_forget_me(
    monkeypatch: pytest.MonkeyPatch,
    test_db: Database,
) -> None:
    """Start help and command menu include forget me."""
    settings = make_settings(SUPERVISOR_ID=999999999)
    monkeypatch.setattr(test_db, "get_admin_ids", AsyncMock(return_value=set()))

    user_id = 123456789
    response = SimpleNamespace(message_id=42)
    answer = AsyncMock(return_value=response)
    set_my_commands = AsyncMock()
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(id=user_id),
        bot=SimpleNamespace(set_my_commands=set_my_commands),
        answer=answer,
    )
    state = SimpleNamespace(update_data=AsyncMock())

    await cmd_start(message, state, settings, test_db)

    commands = set_my_commands.await_args.kwargs["commands"]
    assert any(command.command == "forget_me" for command in commands)
    assert "/forget_me — удалить все свои данные" in answer.await_args.args[0]


@pytest.mark.asyncio
async def test_start_adds_ban_commands_for_admins(
    monkeypatch: pytest.MonkeyPatch,
    test_db: Database,
) -> None:
    """Start adds ban commands for admins."""
    settings = make_settings(SUPERVISOR_ID=999999999)
    admin_id = 111111111
    monkeypatch.setattr(test_db, "get_admin_ids", AsyncMock(return_value={admin_id}))

    response = SimpleNamespace(message_id=42)
    answer = AsyncMock(return_value=response)
    set_my_commands = AsyncMock()
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=admin_id),
        chat=SimpleNamespace(id=admin_id),
        bot=SimpleNamespace(set_my_commands=set_my_commands),
        answer=answer,
    )
    state = SimpleNamespace(update_data=AsyncMock())

    await cmd_start(message, state, settings, test_db)

    commands = {
        command.command for command in set_my_commands.await_args.kwargs["commands"]
    }
    assert {"ban", "unban"} <= commands
    help_text = answer.await_args.args[0]
    assert "/ban ID — заблокировать пользователя" in help_text
    assert "/unban ID — снять блокировку пользователя" in help_text
