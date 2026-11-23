# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fixtures for dispatcher tests."""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import (
    DeleteMessage,
    EditMessageText,
    GetMe,
    SendMessage,
    SetMyCommands,
)
from aiogram.types import User

from bot_obormot.app.routers import configure_dispatcher
from tests.support.dispatcher import (
    SETTINGS,
    AccessDatabase,
    FakeLLM,
    reset_throttle,
)
from tests.support.telegram import (
    FakeTelegramSession,
    make_message,
)


@pytest.fixture
def access_database(
    dispatcher: Dispatcher,
) -> AccessDatabase:
    """Configure an isolated database and open access for dispatcher tests."""
    database = AccessDatabase()
    dispatcher.workflow_data["settings"] = SETTINGS
    dispatcher.workflow_data["llm_client"] = FakeLLM()
    dispatcher.workflow_data["database"] = database
    return database


@pytest.fixture(scope="module")
def dispatcher() -> Iterator[Dispatcher]:
    """Create one configured dispatcher for the test module.

    The application routers are shared module-level objects, so they are
    detached afterwards to keep other test modules independent of the order.
    """
    configured = configure_dispatcher(Dispatcher(storage=MemoryStorage()), SETTINGS)
    yield configured

    for router in configured.sub_routers:
        router._parent_router = None
    configured.sub_routers.clear()


@pytest_asyncio.fixture
async def dispatcher_runtime(
    dispatcher: Dispatcher,
    access_database: AccessDatabase,
) -> AsyncIterator[tuple[Dispatcher, Bot, FakeTelegramSession]]:
    """Create a fake Telegram API session for one dispatcher update."""
    assert isinstance(access_database, AccessDatabase)
    assert dispatcher.workflow_data["settings"] is SETTINGS
    reset_throttle(dispatcher)
    session = FakeTelegramSession(
        {
            DeleteMessage: True,
            EditMessageText: True,
            GetMe: User(id=900, is_bot=True, first_name="Test Bot"),
            SendMessage: make_message(message_id=900),
            SetMyCommands: True,
        }
    )
    bot = Bot(token=SETTINGS.BOT_TOKEN, session=session)

    try:
        yield dispatcher, bot, session
    finally:
        await bot.session.close()
