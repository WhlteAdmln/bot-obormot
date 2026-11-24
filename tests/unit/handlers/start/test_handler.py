# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for start handler."""

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import (
    SetMyCommands,
)

from tests.support.dispatcher import (
    ADMIN_ID,
    SUPERVISOR_ID,
    USER_ID,
    AccessDatabase,
    feed_command,
    sent_texts,
)
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
    make_update,
)


class _FailingAdminDatabase:
    """Simulate an administrator lookup failure in the start handler."""

    def __init__(self) -> None:
        self.admin_lookup_calls = 0

    @staticmethod
    async def get_blocked_ids() -> set[int]:
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
    expected_fragment = "Привет! 👋 Я бот для работы с LLM в формате чата."
    assert expected_fragment in texts[0]
    expected_fragment = "/forget_me — удалить все свои данные"
    assert expected_fragment in texts[0]
    expected_fragment = "health"
    assert (expected_fragment in command_names) is expected_admin
    assert ({"ban", "unban"} <= command_names) is expected_admin
    expected_fragment = "🩺 Состояние бота:"
    assert (expected_fragment in texts[0]) is expected_admin
    assert ({"admin", "admins", "admin_add", "admin_remove"} <= command_names) is (
        expected_supervisor
    )
    expected_fragment = "🛠 Управление администраторами:"
    assert (expected_fragment in texts[0]) is expected_supervisor


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
    expected_fragment = "Привет! 👋 Я бот для работы с LLM в формате чата."
    assert expected_fragment in texts[0]
    expected_fragment = "health"
    assert expected_fragment not in command_names
    expected_fragment = "🩺 Состояние бота:"
    assert expected_fragment not in texts[0]
    expected_fragment = "admin"
    assert expected_fragment not in command_names
    expected_fragment = "🛠 Управление администраторами:"
    assert expected_fragment not in texts[0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_start_menu_offers_forget_me(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await feed_command(dispatcher_runtime, USER_ID + 3, "/start")

    expected_command = "forget_me"
    assert expected_command in _sent_command_names(session), "forget_me is missing"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_start_help_explains_forget_me(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await feed_command(dispatcher_runtime, USER_ID + 4, "/start")

    expected_line = "/forget_me — удалить все свои данные"
    assert expected_line in sent_texts(session)[0], "help does not explain forget_me"


@pytest.mark.asyncio
async def test_start_menu_offers_ban_commands_to_admins(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    admin_id = ADMIN_ID + 7
    access_database.admin_ids = {admin_id}

    session = await feed_command(dispatcher_runtime, admin_id, "/start")

    expected_commands = {"ban", "unban"}
    assert expected_commands <= _sent_command_names(session), "ban commands missing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expected_line",
    [
        "/ban ID — заблокировать пользователя",
        "/unban ID — снять блокировку пользователя",
    ],
)
async def test_start_help_explains_ban_commands_to_admins(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    expected_line: str,
) -> None:
    admin_id = ADMIN_ID + 8
    access_database.admin_ids = {admin_id}

    session = await feed_command(dispatcher_runtime, admin_id, "/start")

    assert expected_line in sent_texts(session)[0], "help misses a ban command"
