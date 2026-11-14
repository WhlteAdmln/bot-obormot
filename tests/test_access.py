# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for access."""

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from types import SimpleNamespace

import pytest
import pytest_asyncio
from aiogram.enums import ChatType

from bot.config import config
from bot.middlewares import access as access_module
from bot.services.database import Database

SUPERVISOR_ID = 999999999
ADMIN_ID = 111111111
ALLOWED_USER_ID = 222222222
OUTSIDER_ID = 333333333


class FakeEvent:
    """Fake event."""

    def __init__(self) -> None:
        """Initializes the test double."""
        self.answers = []

    async def answer(self, text: str) -> None:
        """Answer."""
        self.answers.append(text)


@pytest.fixture
def fake_event() -> FakeEvent:
    """Fake event."""
    return FakeEvent()


@pytest.fixture
def fake_handler() -> tuple[object, ...]:
    """Fake handler."""
    calls = []

    async def handler(_event: object, _data: object) -> str:
        calls.append(True)
        return "allowed"

    return handler, calls


@pytest_asyncio.fixture
async def test_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Database]:
    """Создаёт отдельную временную базу данных."""
    monkeypatch.setattr(
        config,
        "DATABASE_PATH",
        str(tmp_path / "access_test.db"),
    )

    monkeypatch.setattr(config, "SUPERVISOR_ID", SUPERVISOR_ID)
    monkeypatch.setattr(config, "ADMIN_IDS", set())
    monkeypatch.setattr(
        config,
        "DEFAULT_SYSTEM_PROMPT",
        "Тестовый промпт",
    )

    database = Database()
    await database.connect()

    monkeypatch.setattr(access_module, "db", database)

    yield database

    await database.close()


@pytest.fixture
def configure_allowlist(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Configure allowlist."""

    def configure(user_ids: object, *, allow_all: bool = False) -> None:
        monkeypatch.setattr(config, "ALLOWED_USERS", set(user_ids))
        monkeypatch.setattr(config, "ALLOW_ALL_USERS", allow_all)

    return configure


async def run_middleware(
    user_id: int,
    event: object,
    handler: object,
    calls: object,
    chat_type: object = ChatType.PRIVATE,
) -> tuple[object, ...]:
    """Run middleware."""
    middleware = access_module.AccessMiddleware()

    data = {
        "event_from_user": (
            SimpleNamespace(id=user_id) if user_id is not None else None
        ),
        "event_chat": SimpleNamespace(type=chat_type),
    }

    result = await middleware(handler, event, data)

    return result, calls


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_supervisor_access(
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Supervisor всегда получает доступ."""
    configure_allowlist([])

    handler, calls = fake_handler

    result, _ = await run_middleware(
        SUPERVISOR_ID,
        fake_event,
        handler,
        calls,
    )

    assert result == "allowed"
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
async def test_admin_access(
    test_database: Database,
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Обычный администратор получает доступ."""
    configure_allowlist([ALLOWED_USER_ID])

    await test_database.add_admin(ADMIN_ID)

    handler, calls = fake_handler

    result, _ = await run_middleware(
        ADMIN_ID,
        fake_event,
        handler,
        calls,
    )

    assert result == "allowed"
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_allowed_user_access(
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Пользователь из ALLOWED_USERS получает доступ."""
    configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result, _ = await run_middleware(
        ALLOWED_USER_ID,
        fake_event,
        handler,
        calls,
    )

    assert result == "allowed"
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_outsider_denied(
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Посторонний пользователь получает отказ."""
    configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result, _ = await run_middleware(
        OUTSIDER_ID,
        fake_event,
        handler,
        calls,
    )

    assert result is None
    assert calls == []
    assert len(fake_event.answers) == 1
    assert "нет доступа" in fake_event.answers[0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_empty_allowlist_denies_access_by_default(
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Пустой allowlist не открывает доступ посторонним."""
    configure_allowlist([])

    handler, calls = fake_handler

    result, _ = await run_middleware(
        OUTSIDER_ID,
        fake_event,
        handler,
        calls,
    )

    assert result is None
    assert calls == []
    assert len(fake_event.answers) == 1
    assert "нет доступа" in fake_event.answers[0]


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_open_access_requires_explicit_flag(
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Открытый доступ включается только явным флагом."""
    configure_allowlist([], allow_all=True)

    handler, calls = fake_handler

    result, _ = await run_middleware(
        OUTSIDER_ID,
        fake_event,
        handler,
        calls,
    )

    assert result == "allowed"
    assert len(calls) == 1
    assert fake_event.answers == []


@pytest.mark.asyncio
async def test_admin_changes_apply_immediately(
    test_database: Database,
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
) -> None:
    """Добавление и удаление администратора действуют сразу."""
    configure_allowlist([ALLOWED_USER_ID])

    middleware = access_module.AccessMiddleware()

    async def handler(_event: object, _data: object) -> str:
        return "allowed"

    data = {"event_from_user": SimpleNamespace(id=ADMIN_ID)}

    # До добавления администратора доступ запрещён.
    result = await middleware(handler, fake_event, data)

    assert result is None

    # Добавляем администратора.
    await test_database.add_admin(ADMIN_ID)

    result = await middleware(handler, fake_event, data)

    assert result == "allowed"

    # Удаляем администратора.
    await test_database.remove_admin(ADMIN_ID)

    result = await middleware(handler, fake_event, data)

    assert result is None


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_event_without_user_is_rejected(
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Событие без пользователя не передаётся обработчикам."""
    configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result, _ = await run_middleware(
        None,
        fake_event,
        handler,
        calls,
    )

    assert result is None
    assert calls == []
    assert fake_event.answers == []


@pytest.mark.parametrize("chat_type", [ChatType.GROUP, ChatType.SUPERGROUP])
@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_group_chat_is_rejected(
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
    chat_type: object,
) -> None:
    """Бот не обрабатывает сообщения в группах и супергруппах."""
    configure_allowlist([ALLOWED_USER_ID])

    handler, calls = fake_handler

    result, _ = await run_middleware(
        ALLOWED_USER_ID,
        fake_event,
        handler,
        calls,
        chat_type=chat_type,
    )

    assert result is None
    assert calls == []
    assert fake_event.answers == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("test_database")
async def test_denied_notice_is_rate_limited(
    configure_allowlist: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Повторный отказ одному пользователю отправляется не чаще минуты."""
    configure_allowlist([])
    middleware = access_module.AccessMiddleware()
    current_time = 100.0
    monkeypatch.setattr(access_module.time, "monotonic", lambda: current_time)

    async def handler(_event: object, _data: object) -> None:
        pytest.fail("Запрещённое сообщение не должно попасть в handler")

    data = {
        "event_from_user": SimpleNamespace(id=OUTSIDER_ID),
        "event_chat": SimpleNamespace(type=ChatType.PRIVATE),
    }

    first_event = FakeEvent()
    second_event = FakeEvent()
    third_event = FakeEvent()

    assert await middleware(handler, first_event, data) is None
    assert await middleware(handler, second_event, data) is None
    assert first_event.answers == ["⛔ У тебя нет доступа к этому боту."]
    assert second_event.answers == []

    current_time += access_module.DENY_NOTICE_INTERVAL
    assert await middleware(handler, third_event, data) is None
    assert third_event.answers == ["⛔ У тебя нет доступа к этому боту."]


@pytest.mark.asyncio
async def test_block_and_unblock_apply_immediately(
    test_database: Database,
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
) -> None:
    """Block and unblock apply immediately."""
    configure_allowlist([ALLOWED_USER_ID], allow_all=True)
    middleware = access_module.AccessMiddleware()
    calls = []

    async def handler(_event: object, _data: object) -> str:
        calls.append(True)
        return "allowed"

    data = {
        "event_from_user": SimpleNamespace(id=ALLOWED_USER_ID),
        "event_chat": SimpleNamespace(type=ChatType.PRIVATE),
    }

    assert await middleware(handler, fake_event, data) == "allowed"
    assert await test_database.block_user(ALLOWED_USER_ID) is True
    assert await middleware(handler, fake_event, data) is None
    assert len(fake_event.answers) == 1
    assert await test_database.unblock_user(ALLOWED_USER_ID) is True
    assert await middleware(handler, fake_event, data) == "allowed"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_supervisor_cannot_be_blocked(
    test_database: Database,
    configure_allowlist: Callable[..., None],
    fake_event: FakeEvent,
    fake_handler: tuple[object, ...],
) -> None:
    """Supervisor cannot be blocked."""
    configure_allowlist([])
    assert await test_database.block_user(SUPERVISOR_ID) is False
    handler, calls = fake_handler
    result, _ = await run_middleware(
        SUPERVISOR_ID,
        fake_event,
        handler,
        calls,
    )
    assert result == "allowed"
