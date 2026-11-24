# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for middlewares access."""

from collections.abc import Iterable
from dataclasses import replace
from types import SimpleNamespace

import pytest
from aiogram import Bot, Dispatcher
from aiogram.enums import ChatType
from aiogram.methods import SetMyCommands

from bot_obormot.handlers.admin.handler import access as admin_access
from bot_obormot.middlewares import access as access_module
from bot_obormot.middlewares.texts import ACCESS_DENIED_MESSAGE
from bot_obormot.settings import Settings
from tests.support.access_database import FakeAccessDatabase
from tests.support.dispatcher import ADMIN_ID, SETTINGS, SUPERVISOR_ID, sent_texts
from tests.support.handler_messages import FakeMessage
from tests.support.middleware_handler import RecordingHandler
from tests.support.settings import make_settings
from tests.support.telegram import FakeTelegramSession, make_message, make_update

OUTSIDER_ID = 333333333

ALLOWED_USER_ID = 222222222

BLOCKED_USER_ID = 444444444

OUTSIDER_COMMANDS = ["/start", "/unknown 123", "/admin_add 333333333", "/ban 1"]


def _settings(
    allowed_users: Iterable[int] = (), *, allow_all: bool = False
) -> Settings:
    return make_settings(
        SUPERVISOR_ID=SUPERVISOR_ID,
        ALLOWED_USERS=set(allowed_users),
        ALLOW_ALL_USERS=allow_all,
    )


def _data(
    user_id: int | None,
    settings: Settings,
    database: FakeAccessDatabase,
    chat_type: str | None = ChatType.PRIVATE,
) -> dict[str, object]:
    return {
        "event_from_user": None if user_id is None else SimpleNamespace(id=user_id),
        "event_chat": None if chat_type is None else SimpleNamespace(type=chat_type),
        "settings": settings,
        "database": database,
    }


async def _deny_notices(
    monkeypatch: pytest.MonkeyPatch, visits: list[tuple[float, int]]
) -> list[list[str]]:
    middleware = access_module.AccessMiddleware()
    settings = _settings()
    database = FakeAccessDatabase()
    answers: list[list[str]] = []
    for moment, user_id in visits:
        monkeypatch.setattr(access_module.time, "monotonic", lambda at=moment: at)
        event = FakeMessage(user_id)
        await middleware(RecordingHandler(), event, _data(user_id, settings, database))
        answers.append(event.answers)
    return answers


async def _middleware_passes(
    user_id: int, settings: Settings, database: FakeAccessDatabase
) -> bool:
    handler = RecordingHandler(result=True)
    result = await access_module.AccessMiddleware()(
        handler, FakeMessage(user_id), _data(user_id, settings, database)
    )
    return result is True


async def _command_allowed(
    command_class: str,
    user_id: int,
    settings: Settings,
    database: FakeAccessDatabase,
) -> bool:
    gates = {
        "ordinary": lambda: True,
        "supervisor": lambda: admin_access.is_supervisor(
            SimpleNamespace(from_user=SimpleNamespace(id=user_id)), settings
        ),
    }
    if command_class in gates:
        return gates[command_class]()
    return await admin_access.is_admin_or_supervisor(user_id, settings, database)


def _general_access(role: str, *, allow_all: bool, allowlist_nonempty: bool) -> bool:
    grants = {
        "supervisor": True,
        "admin": True,
        "allowed": allowlist_nonempty or allow_all,
        "blocked": False,
        "stranger": allow_all,
    }
    return grants[role]


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize("command_text", OUTSIDER_COMMANDS)
async def test_dispatcher_answers_outsider_commands_with_a_denial(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
) -> None:
    dispatcher, bot, session = dispatcher_runtime
    dispatcher.workflow_data["settings"] = replace(SETTINGS, ALLOW_ALL_USERS=False)
    update = make_update(message=make_message(user_id=OUTSIDER_ID, text=command_text))
    await dispatcher.feed_update(bot, update)
    expected = [ACCESS_DENIED_MESSAGE]
    assert sent_texts(session) == expected, "an outsider got more than a denial"


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize("command_text", OUTSIDER_COMMANDS)
async def test_dispatcher_sets_no_commands_for_an_outsider(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    command_text: str,
) -> None:
    dispatcher, bot, session = dispatcher_runtime
    dispatcher.workflow_data["settings"] = replace(SETTINGS, ALLOW_ALL_USERS=False)
    update = make_update(message=make_message(user_id=OUTSIDER_ID, text=command_text))
    await dispatcher.feed_update(bot, update)
    menus = [
        request for request in session.requests if isinstance(request, SetMyCommands)
    ]
    expected_empty: list[SetMyCommands] = []
    assert menus == expected_empty, "an outsider changed the command menu"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "allowed_users", "allow_all", "admin_ids", "blocked_ids", "chat"),
    [
        (SUPERVISOR_ID, set(), False, set(), set(), ChatType.PRIVATE),
        (SUPERVISOR_ID, set(), False, set(), {SUPERVISOR_ID}, ChatType.PRIVATE),
        (ADMIN_ID, {ALLOWED_USER_ID}, False, {ADMIN_ID}, set(), ChatType.PRIVATE),
        (ALLOWED_USER_ID, {ALLOWED_USER_ID}, False, set(), set(), ChatType.PRIVATE),
        (OUTSIDER_ID, set(), True, set(), set(), ChatType.PRIVATE),
        (ALLOWED_USER_ID, {ALLOWED_USER_ID}, False, set(), set(), None),
    ],
    ids=[
        "supervisor-empty-allowlist",
        "supervisor-listed-as-blocked",
        "database-admin",
        "allowlisted",
        "open-access",
        "no-chat",
    ],
)
async def test_passes_the_event_of_a_user_with_access(
    user_id: int,
    allowed_users: set[int],
    *,
    allow_all: bool,
    admin_ids: set[int],
    blocked_ids: set[int],
    chat: str | None,
) -> None:
    database = FakeAccessDatabase(admin_ids=admin_ids, blocked_ids=blocked_ids)
    handler = RecordingHandler()
    event = FakeMessage(user_id)
    data = _data(user_id, _settings(allowed_users, allow_all=allow_all), database, chat)
    result = await access_module.AccessMiddleware()(handler, event, data)
    expected = ("handled", [event], [])
    actual = (result, handler.events, event.answers)
    assert actual == expected, "a user with access was stopped"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "allowed_users", "allow_all", "admin_ids", "blocked_ids"),
    [
        (OUTSIDER_ID, {ALLOWED_USER_ID}, False, set(), set()),
        (OUTSIDER_ID, set(), False, set(), set()),
        (BLOCKED_USER_ID, {BLOCKED_USER_ID}, True, set(), {BLOCKED_USER_ID}),
        (ADMIN_ID, set(), False, {ADMIN_ID}, {ADMIN_ID}),
        (-SUPERVISOR_ID, {SUPERVISOR_ID}, False, {SUPERVISOR_ID}, set()),
        (0, {ALLOWED_USER_ID}, False, set(), set()),
        (2**63 - 1, {ALLOWED_USER_ID}, False, set(), set()),
    ],
    ids=[
        "outsider",
        "empty-allowlist",
        "blocked-allowlisted-open",
        "blocked-admin",
        "negated-supervisor",
        "zero",
        "largest-id",
    ],
)
async def test_denies_a_user_without_access_with_one_notice(
    user_id: int,
    allowed_users: set[int],
    *,
    allow_all: bool,
    admin_ids: set[int],
    blocked_ids: set[int],
) -> None:
    database = FakeAccessDatabase(admin_ids=admin_ids, blocked_ids=blocked_ids)
    handler = RecordingHandler()
    event = FakeMessage(user_id)
    data = _data(user_id, _settings(allowed_users, allow_all=allow_all), database)
    result = await access_module.AccessMiddleware()(handler, event, data)
    expected = (None, [], [ACCESS_DENIED_MESSAGE])
    actual = (result, handler.events, event.answers)
    assert actual == expected, "a user without access was not denied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "chat"),
    [
        (None, ChatType.PRIVATE),
        (ALLOWED_USER_ID, ChatType.GROUP),
        (ALLOWED_USER_ID, ChatType.SUPERGROUP),
        (ALLOWED_USER_ID, ChatType.CHANNEL),
        (SUPERVISOR_ID, ChatType.GROUP),
        (ALLOWED_USER_ID, "unknown_chat_type"),
    ],
    ids=[
        "no-sender",
        "group",
        "supergroup",
        "channel",
        "supervisor-in-group",
        "unknown-type",
    ],
)
async def test_drops_silently_before_reading_the_database(
    user_id: int | None, chat: str
) -> None:
    database = FakeAccessDatabase()
    handler = RecordingHandler()
    event = FakeMessage(user_id)
    data = _data(user_id, _settings({ALLOWED_USER_ID}), database, chat)
    result = await access_module.AccessMiddleware()(handler, event, data)
    expected = (None, [], [], [])
    actual = (result, handler.events, event.answers, database.lookups)
    assert actual == expected, "an event outside a private chat was processed"


@pytest.mark.asyncio
async def test_denies_an_event_that_cannot_be_answered() -> None:
    handler = RecordingHandler()
    data = _data(OUTSIDER_ID, _settings(), FakeAccessDatabase())
    result = await access_module.AccessMiddleware()(handler, object(), data)
    expected = (None, [])
    assert (result, handler.events) == expected, "an unanswerable event was passed on"


@pytest.mark.asyncio
async def test_applies_admin_changes_to_the_next_event() -> None:
    database = FakeAccessDatabase()
    middleware = access_module.AccessMiddleware()
    data = _data(ADMIN_ID, _settings({ALLOWED_USER_ID}), database)
    results = [await middleware(RecordingHandler(), FakeMessage(ADMIN_ID), data)]
    database.admin_ids.add(ADMIN_ID)
    results.append(await middleware(RecordingHandler(), FakeMessage(ADMIN_ID), data))
    database.admin_ids.discard(ADMIN_ID)
    results.append(await middleware(RecordingHandler(), FakeMessage(ADMIN_ID), data))
    expected = [None, "handled", None]
    assert results == expected, "an admin change took effect late"


@pytest.mark.asyncio
async def test_applies_blocks_to_the_next_event() -> None:
    database = FakeAccessDatabase()
    middleware = access_module.AccessMiddleware()
    settings = _settings({ALLOWED_USER_ID}, allow_all=True)
    data = _data(ALLOWED_USER_ID, settings, database)
    event = FakeMessage(ALLOWED_USER_ID)
    results = [await middleware(RecordingHandler(), event, data)]
    database.blocked_ids.add(ALLOWED_USER_ID)
    results.append(await middleware(RecordingHandler(), event, data))
    database.blocked_ids.discard(ALLOWED_USER_ID)
    results.append(await middleware(RecordingHandler(), event, data))
    expected = ["handled", None, "handled"]
    assert results == expected, "a block change took effect late"


@pytest.mark.asyncio
async def test_rate_limits_the_denial_notice(monkeypatch: pytest.MonkeyPatch) -> None:
    interval = access_module.DENY_NOTICE_INTERVAL
    visits = [
        (100.0, OUTSIDER_ID),
        (100.0, OUTSIDER_ID),
        (100.0 + interval - 0.001, OUTSIDER_ID),
        (100.0 + interval, OUTSIDER_ID),
    ]
    answers = await _deny_notices(monkeypatch, visits)
    expected = [[ACCESS_DENIED_MESSAGE], [], [], [ACCESS_DENIED_MESSAGE]]
    assert answers == expected, "the denial notice ignores its interval"


@pytest.mark.asyncio
async def test_rate_limits_the_denial_notice_per_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    visits = [(50.0, OUTSIDER_ID), (50.0, OUTSIDER_ID + 1), (50.0, OUTSIDER_ID)]
    answers = await _deny_notices(monkeypatch, visits)
    expected = [[ACCESS_DENIED_MESSAGE], [ACCESS_DENIED_MESSAGE], []]
    assert answers == expected, "one user's notice silenced another user"


@pytest.mark.asyncio
async def test_forgets_denied_users_when_the_table_is_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = 10_000_000
    flood = [
        (7.0, first + offset) for offset in range(access_module.MAX_TRACKED_DENIED)
    ]
    visits = [*flood, (7.0, first - 1), (7.0, first)]
    answers = await _deny_notices(monkeypatch, visits)
    expected = [ACCESS_DENIED_MESSAGE]
    assert answers[-1] == expected, "the denied-user table grew past its limit"


@pytest.mark.parametrize(
    ("role", "user_id"),
    [
        ("supervisor", SUPERVISOR_ID),
        ("admin", ADMIN_ID),
        ("allowed", ALLOWED_USER_ID),
        ("blocked", BLOCKED_USER_ID),
        ("stranger", OUTSIDER_ID),
    ],
    ids=["supervisor", "admin", "allowed", "blocked", "stranger"],
)
@pytest.mark.parametrize("allow_all", [False, True], ids=["closed", "open"])
@pytest.mark.parametrize("allowlist_nonempty", [False, True], ids=["empty", "nonempty"])
@pytest.mark.parametrize(
    ("command_class", "command_roles"),
    [
        ("ordinary", {"supervisor", "admin", "allowed", "blocked", "stranger"}),
        ("admin", {"supervisor", "admin"}),
        ("supervisor", {"supervisor"}),
    ],
    ids=["ordinary", "admin", "supervisor"],
)
@pytest.mark.asyncio
async def test_applies_access_rules_to_every_role_and_command(
    role: str,
    user_id: int,
    *,
    allow_all: bool,
    allowlist_nonempty: bool,
    command_class: str,
    command_roles: set[str],
) -> None:
    database = FakeAccessDatabase(admin_ids={ADMIN_ID}, blocked_ids={BLOCKED_USER_ID})
    settings = _settings(
        {ALLOWED_USER_ID} if allowlist_nonempty else set(), allow_all=allow_all
    )
    general = _general_access(
        role, allow_all=allow_all, allowlist_nonempty=allowlist_nonempty
    )
    actual = (
        await _middleware_passes(user_id, settings, database),
        await _command_allowed(command_class, user_id, settings, database),
    )
    expected = (general, role in command_roles)
    assert actual == expected, "the access gates disagree with the matrix"
