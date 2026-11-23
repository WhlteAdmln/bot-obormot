# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for middlewares access."""

from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums import ChatType
from aiogram.methods import (
    SetMyCommands,
)

from bot_obormot.handlers.admin import handler as admin_handler
from bot_obormot.middlewares import access as access_module
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings
from tests.support.dispatcher import ADMIN_ID, SETTINGS, SUPERVISOR_ID, sent_texts
from tests.support.settings import make_settings
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
    make_update,
)

OUTSIDER_ID = 333333333


ALLOWED_USER_ID = 222222222


BLOCKED_USER_ID = 444444444


class FakeEvent:
    """Fake event."""

    def __init__(self) -> None:
        """Initializes the test double."""
        self.answers = []

    async def answer(self, text: str) -> None:
        """Answer."""
        self.answers.append(text)


class AccessMatrixDatabase:
    """Database stub for access matrix tests."""

    def __init__(self, admin_ids: set[int], blocked_ids: set[int]) -> None:
        """Initializes the test database."""
        self.admin_ids = admin_ids
        self.blocked_ids = blocked_ids

    async def get_blocked_ids(self) -> set[int]:
        """Returns blocked user IDs."""
        return self.blocked_ids

    async def get_admin_ids(self) -> set[int]:
        """Returns administrator IDs."""
        return self.admin_ids


@pytest.fixture(name="fake_event")
def fixture_fake_event() -> FakeEvent:
    """Fake event."""
    return FakeEvent()


@pytest.fixture(name="fake_handler")
def fixture_fake_handler() -> tuple[object, ...]:
    """Fake handler."""
    calls = []

    async def handler(_event: object, _data: object) -> str:
        calls.append(True)
        return "allowed"

    return handler, calls


@pytest_asyncio.fixture(name="test_database")
async def fixture_test_database(tmp_path: Path) -> AsyncIterator[Database]:
    """Создаёт отдельную временную базу данных."""
    settings = make_settings(
        DATABASE_PATH=str(tmp_path / "access_test.db"),
        SUPERVISOR_ID=SUPERVISOR_ID,
        ADMIN_IDS=set(),
        DEFAULT_SYSTEM_PROMPT="Тестовый промпт",
    )

    database = Database(settings)
    await database.connect()

    yield database

    await database.close()


@pytest.fixture(name="configure_allowlist")
def fixture_configure_allowlist() -> Callable[..., Settings]:
    """Build settings with the requested allowlist."""

    def configure(user_ids: object, *, allow_all: bool = False) -> Settings:
        return make_settings(
            SUPERVISOR_ID=SUPERVISOR_ID,
            ALLOWED_USERS=set(user_ids),
            ALLOW_ALL_USERS=allow_all,
        )

    return configure


async def run_middleware(
    settings: Settings,
    user_id: int,
    event: object,
    handler: object,
    database: object,
    chat_type: object = ChatType.PRIVATE,
) -> object:
    """Run middleware."""
    middleware = access_module.AccessMiddleware()

    data = {
        "event_from_user": (
            SimpleNamespace(id=user_id) if user_id is not None else None
        ),
        "event_chat": SimpleNamespace(type=chat_type),
        "settings": settings,
        "database": database,
    }

    return await middleware(handler, event, data)


@pytest.mark.asyncio
@pytest.mark.usefixtures("access_database")
@pytest.mark.parametrize(
    "case",
    [(OUTSIDER_ID, "/start"), (OUTSIDER_ID + 1, "/unknown 123")],
)
async def test_dispatcher_denies_commands_without_access(
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    case: tuple[int, str],
) -> None:
    """Access middleware rejects both known and unknown commands."""
    dispatcher, bot, session = dispatcher_runtime
    user_id, command_text = case
    dispatcher.workflow_data["settings"] = replace(SETTINGS, ALLOW_ALL_USERS=False)

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=user_id, text=command_text)),
    )

    assert sent_texts(session) == ["⛔ У тебя нет доступа к этому боту."]
    assert not any(isinstance(request, SetMyCommands) for request in session.requests)


@pytest.mark.asyncio
async def test_supervisor_access(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Supervisor всегда получает доступ."""
    settings = configure_allowlist([])

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        SUPERVISOR_ID,
        fake_event,
        handler,
        database=test_database,
    )

    expected_result = "allowed"
    assert result == expected_result
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
async def test_admin_access(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Обычный администратор получает доступ."""
    settings = configure_allowlist([ALLOWED_USER_ID])

    await test_database.add_admin(ADMIN_ID)

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        ADMIN_ID,
        fake_event,
        handler,
        database=test_database,
    )

    expected_result = "allowed"
    assert result == expected_result
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
async def test_allowed_user_access(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Пользователь из ALLOWED_USERS получает доступ."""
    settings = configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        ALLOWED_USER_ID,
        fake_event,
        handler,
        database=test_database,
    )

    expected_result = "allowed"
    assert result == expected_result
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
async def test_outsider_denied(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Посторонний пользователь получает отказ."""
    settings = configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        OUTSIDER_ID,
        fake_event,
        handler,
        database=test_database,
    )

    assert result is None
    assert calls == []
    assert len(fake_event.answers) == 1
    expected_fragment = "нет доступа"
    assert expected_fragment in fake_event.answers[0]


@pytest.mark.asyncio
async def test_empty_allowlist_denies_access_by_default(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Пустой allowlist не открывает доступ посторонним."""
    settings = configure_allowlist([])

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        OUTSIDER_ID,
        fake_event,
        handler,
        database=test_database,
    )

    assert result is None
    assert calls == []
    assert len(fake_event.answers) == 1
    expected_fragment = "нет доступа"
    assert expected_fragment in fake_event.answers[0]


@pytest.mark.asyncio
async def test_open_access_requires_explicit_flag(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Открытый доступ включается только явным флагом."""
    settings = configure_allowlist([], allow_all=True)

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        OUTSIDER_ID,
        fake_event,
        handler,
        database=test_database,
    )

    expected_result = "allowed"
    assert result == expected_result
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
async def test_admin_changes_apply_immediately(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
) -> None:
    """Добавление и удаление администратора действуют сразу."""
    settings = configure_allowlist([ALLOWED_USER_ID])

    middleware = access_module.AccessMiddleware()

    async def handler(_event: object, _data: object) -> str:
        return "allowed"

    data = {
        "event_from_user": SimpleNamespace(id=ADMIN_ID),
        "settings": settings,
        "database": test_database,
    }

    # До добавления администратора доступ запрещён.
    result = await middleware(handler, fake_event, data)

    assert result is None

    # Добавляем администратора.
    await test_database.add_admin(ADMIN_ID)

    result = await middleware(handler, fake_event, data)

    expected_result = "allowed"
    assert result == expected_result

    # Удаляем администратора.
    await test_database.remove_admin(ADMIN_ID)

    result = await middleware(handler, fake_event, data)

    assert result is None


@pytest.mark.asyncio
async def test_event_without_user_is_rejected(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Событие без пользователя не передаётся обработчикам."""
    settings = configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        None,
        fake_event,
        handler,
        database=test_database,
    )

    assert result is None
    assert calls == []
    assert fake_event.answers == []


@pytest.mark.parametrize("chat_type", [ChatType.GROUP, ChatType.SUPERGROUP])
@pytest.mark.asyncio
async def test_group_chat_is_rejected(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
    chat_type: object,
) -> None:
    """Бот не обрабатывает сообщения в группах и супергруппах."""
    settings = configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result = await run_middleware(
        settings,
        ALLOWED_USER_ID,
        fake_event,
        handler,
        database=test_database,
        chat_type=chat_type,
    )

    assert result is None
    assert calls == []
    assert fake_event.answers == []


@pytest.mark.asyncio
async def test_denied_notice_is_rate_limited(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Повторный отказ одному пользователю отправляется не чаще минуты."""
    settings = configure_allowlist([])
    middleware = access_module.AccessMiddleware()
    current_time = 100.0
    monkeypatch.setattr(access_module.time, "monotonic", lambda: current_time)

    async def handler(_event: object, _data: object) -> None:
        pytest.fail("Запрещённое сообщение не должно попасть в handler")

    data = {
        "event_from_user": SimpleNamespace(id=OUTSIDER_ID),
        "event_chat": SimpleNamespace(type=ChatType.PRIVATE),
        "settings": settings,
        "database": test_database,
    }

    first_event = FakeEvent()
    second_event = FakeEvent()
    third_event = FakeEvent()

    assert await middleware(handler, first_event, data) is None
    assert await middleware(handler, second_event, data) is None
    assert first_event.answers == ["⛔ У тебя нет доступа к этому боту."]
    expected_empty = []
    assert second_event.answers == expected_empty, "expected an empty list"

    current_time += access_module.DENY_NOTICE_INTERVAL
    assert await middleware(handler, third_event, data) is None
    assert third_event.answers == ["⛔ У тебя нет доступа к этому боту."]


@pytest.mark.asyncio
async def test_block_and_unblock_apply_immediately(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
) -> None:
    """Block and unblock apply immediately."""
    settings = configure_allowlist([ALLOWED_USER_ID], allow_all=True)
    middleware = access_module.AccessMiddleware()
    calls = []

    async def handler(_event: object, _data: object) -> str:
        calls.append(True)
        return "allowed"

    data = {
        "event_from_user": SimpleNamespace(id=ALLOWED_USER_ID),
        "event_chat": SimpleNamespace(type=ChatType.PRIVATE),
        "settings": settings,
        "database": test_database,
    }

    expected_text = "allowed"
    assert await middleware(handler, fake_event, data) == expected_text
    assert await test_database.block_user(ALLOWED_USER_ID) is True
    assert await middleware(handler, fake_event, data) is None
    assert len(fake_event.answers) == 1
    assert await test_database.unblock_user(ALLOWED_USER_ID) is True
    expected_text = "allowed"
    assert await middleware(handler, fake_event, data) == expected_text
    expected_count = 2
    assert len(calls) == expected_count


@pytest.mark.asyncio
async def test_supervisor_cannot_be_blocked(
    test_database: Database,
    configure_allowlist: Callable[..., Settings],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Supervisor cannot be blocked."""
    settings = configure_allowlist([])
    assert await test_database.block_user(SUPERVISOR_ID) is False
    handler, _calls = fake_handler
    result = await run_middleware(
        settings,
        SUPERVISOR_ID,
        fake_event,
        handler,
        database=test_database,
    )
    expected_result = "allowed"
    assert result == expected_result


async def _middleware_passes(
    user_id: int, settings: Settings, database: object
) -> bool:
    async def handler(_event: object, _data: object) -> bool:
        return True

    data = {
        "event_from_user": SimpleNamespace(id=user_id),
        "event_chat": SimpleNamespace(type=ChatType.PRIVATE),
        "settings": settings,
        "database": database,
    }
    result = await access_module.AccessMiddleware()(handler, FakeEvent(), data)
    return result is True


async def _command_allowed(
    command_class: str,
    user_id: int,
    settings: Settings,
    database: object,
) -> bool:
    gates = {
        "ordinary": lambda: True,
        "supervisor": lambda: admin_handler.is_supervisor(
            SimpleNamespace(from_user=SimpleNamespace(id=user_id)), settings
        ),
    }
    if command_class in gates:
        return gates[command_class]()
    return await admin_handler.is_admin_or_supervisor(user_id, settings, database)


def _general_access(role: str, *, allow_all: bool, allowlist_nonempty: bool) -> bool:
    grants = {
        "supervisor": True,
        "admin": True,
        "allowed": allowlist_nonempty or allow_all,
        "blocked": False,
        "stranger": allow_all,
    }
    return grants[role]


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
async def test_access_matrix(
    role: str,
    user_id: int,
    *,
    allow_all: bool,
    allowlist_nonempty: bool,
    command_class: str,
    command_roles: set[str],
) -> None:
    database = AccessMatrixDatabase(admin_ids={ADMIN_ID}, blocked_ids={BLOCKED_USER_ID})
    settings = make_settings(
        SUPERVISOR_ID=SUPERVISOR_ID,
        ALLOWED_USERS={ALLOWED_USER_ID} if allowlist_nonempty else set(),
        ALLOW_ALL_USERS=allow_all,
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
