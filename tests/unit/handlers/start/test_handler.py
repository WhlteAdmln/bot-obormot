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


def _command_menus(session: FakeTelegramSession) -> list[SetMyCommands]:
    """Return the outgoing SetMyCommands requests."""
    return [
        request for request in session.requests if isinstance(request, SetMyCommands)
    ]


def _sent_command_names(session: FakeTelegramSession) -> set[str]:
    """Extract command names from the outgoing SetMyCommands requests."""
    return {
        command.command
        for request in _command_menus(session)
        for command in request.commands
    }


async def _start_as(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str],
) -> FakeTelegramSession:
    """Send a start command as a user with the given administrators."""
    user_id, admin_ids, command_text = case
    access_database.admin_ids = admin_ids
    return await feed_command(dispatcher_runtime, user_id, command_text)


async def _start_with_failing_database(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    user_id: int,
) -> FakeTelegramSession:
    """Send a start command while the administrator lookup fails."""
    dispatcher, bot, session = dispatcher_runtime
    dispatcher.workflow_data["database"] = _FailingAdminDatabase()
    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text="/start")),
    )
    return session


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 1, set(), "/start"),
        (ADMIN_ID + 1, {ADMIN_ID + 1}, "/start"),
        (SUPERVISOR_ID, set(), "/start"),
        (USER_ID + 2, set(), "/start extra arguments"),
    ],
)
async def test_start_sends_one_message(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str],
) -> None:
    session = await _start_as(access_database, dispatcher_runtime, case)
    expected_count = 1
    assert len(sent_texts(session)) == expected_count, "start sent a wrong count"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 11, set(), "/start"),
        (ADMIN_ID + 11, {ADMIN_ID + 11}, "/start"),
        (SUPERVISOR_ID, set(), "/start"),
        (USER_ID + 12, set(), "/start extra arguments"),
    ],
)
async def test_start_greets_every_user(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str],
) -> None:
    session = await _start_as(access_database, dispatcher_runtime, case)
    greeting = "Привет! 👋 Я бот для работы с LLM в формате чата."
    assert greeting in sent_texts(session)[0], "start does not greet the user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 21, set(), "/start"),
        (ADMIN_ID + 21, {ADMIN_ID + 21}, "/start"),
        (SUPERVISOR_ID, set(), "/start"),
        (USER_ID + 22, set(), "/start extra arguments"),
    ],
)
async def test_start_help_lists_forget_me_for_every_user(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str],
) -> None:
    session = await _start_as(access_database, dispatcher_runtime, case)
    forget_me_line = "/forget_me — удалить все свои данные"
    assert forget_me_line in sent_texts(session)[0], "help misses forget_me"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 31, set(), "/start"),
        (ADMIN_ID + 31, {ADMIN_ID + 31}, "/start"),
        (SUPERVISOR_ID, set(), "/start"),
        (USER_ID + 32, set(), "/start extra arguments"),
    ],
)
async def test_start_sets_one_command_menu(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str],
) -> None:
    session = await _start_as(access_database, dispatcher_runtime, case)
    expected_count = 1
    assert len(_command_menus(session)) == expected_count, "wrong menu count"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 41, set(), "/start", False),
        (ADMIN_ID + 41, {ADMIN_ID + 41}, "/start", True),
        (SUPERVISOR_ID, set(), "/start", True),
        (USER_ID + 42, set(), "/start extra arguments", False),
    ],
)
async def test_start_menu_offers_health_commands_only_to_admins(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str, bool],
) -> None:
    user_id, admin_ids, command_text, expected = case
    session = await _start_as(
        access_database, dispatcher_runtime, (user_id, admin_ids, command_text)
    )
    admin_commands = {"health", "ban", "unban"}
    offered = admin_commands <= _sent_command_names(session)
    assert offered is expected, "admin commands are offered to the wrong user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 51, set(), "/start", False),
        (ADMIN_ID + 51, {ADMIN_ID + 51}, "/start", True),
        (SUPERVISOR_ID, set(), "/start", True),
        (USER_ID + 52, set(), "/start extra arguments", False),
    ],
)
async def test_start_help_shows_health_section_only_to_admins(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str, bool],
) -> None:
    user_id, admin_ids, command_text, expected = case
    session = await _start_as(
        access_database, dispatcher_runtime, (user_id, admin_ids, command_text)
    )
    health_section = "🩺 Состояние бота:"
    shown = health_section in sent_texts(session)[0]
    assert shown is expected, "the health section is shown to the wrong user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 61, set(), "/start", False),
        (ADMIN_ID + 61, {ADMIN_ID + 61}, "/start", False),
        (SUPERVISOR_ID, set(), "/start", True),
        (USER_ID + 62, set(), "/start extra arguments", False),
    ],
)
async def test_start_menu_offers_admin_management_only_to_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str, bool],
) -> None:
    user_id, admin_ids, command_text, expected = case
    session = await _start_as(
        access_database, dispatcher_runtime, (user_id, admin_ids, command_text)
    )
    supervisor_commands = {"admin", "admins", "admin_add", "admin_remove"}
    offered = supervisor_commands <= _sent_command_names(session)
    assert offered is expected, "admin management is offered to the wrong user"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        (USER_ID + 71, set(), "/start", False),
        (ADMIN_ID + 71, {ADMIN_ID + 71}, "/start", False),
        (SUPERVISOR_ID, set(), "/start", True),
        (USER_ID + 72, set(), "/start extra arguments", False),
    ],
)
async def test_start_help_shows_admin_section_only_to_supervisor(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, set[int], str, bool],
) -> None:
    user_id, admin_ids, command_text, expected = case
    session = await _start_as(
        access_database, dispatcher_runtime, (user_id, admin_ids, command_text)
    )
    admin_section = "🛠 Управление администраторами:"
    shown = admin_section in sent_texts(session)[0]
    assert shown is expected, "the admin section is shown to the wrong user"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_start_sends_one_message_when_database_fails(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await _start_with_failing_database(dispatcher_runtime, USER_ID + 81)
    expected_count = 1
    assert len(sent_texts(session)) == expected_count, "start sent a wrong count"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_start_greets_the_user_when_database_fails(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await _start_with_failing_database(dispatcher_runtime, USER_ID + 82)
    greeting = "Привет! 👋 Я бот для работы с LLM в формате чата."
    assert greeting in sent_texts(session)[0], "start does not greet the user"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
async def test_start_sets_one_command_menu_when_database_fails(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    session = await _start_with_failing_database(dispatcher_runtime, USER_ID + 83)
    expected_count = 1
    assert len(_command_menus(session)) == expected_count, "wrong menu count"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize("command", ["health", "admin"])
async def test_start_falls_back_to_regular_menu_when_database_fails(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command: str,
) -> None:
    session = await _start_with_failing_database(dispatcher_runtime, USER_ID + 84)
    assert command not in _sent_command_names(session), "a privileged command leaked"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "section", ["🩺 Состояние бота:", "🛠 Управление администраторами:"]
)
async def test_start_falls_back_to_regular_help_when_database_fails(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    section: str,
) -> None:
    session = await _start_with_failing_database(dispatcher_runtime, USER_ID + 85)
    assert section not in sent_texts(session)[0], "a privileged section leaked"


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
