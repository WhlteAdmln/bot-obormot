# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the /health command."""

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import (
    EditMessageText,
)
from aiogram.types import User

from tests.support.dispatcher import (
    HISTORY_ADMIN_ID,
    HISTORY_USER_ID,
    SUPERVISOR_ID,
    AccessDatabase,
    FakeLLM,
    feed_command,
    sent_texts,
)
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


async def _fail_get_me(_bot: Bot) -> User:
    msg = "Telegram unavailable"
    raise RuntimeError(msg)


async def _feed_health_with_failures(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    monkeypatch: pytest.MonkeyPatch,
) -> FakeTelegramSession:
    dispatcher, bot, session = dispatcher_runtime
    access_database.scenario.failed_operation = "health_check"
    monkeypatch.setattr(Bot, "get_me", _fail_get_me)
    dispatcher.workflow_data["llm_client"] = FakeLLM((False, "Недоступен"))

    await dispatcher.feed_update(
        bot,
        make_update(message=make_message(user_id=SUPERVISOR_ID, text="/health")),
    )
    return session


@pytest.mark.asyncio
async def test_health_sends_a_progress_message(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.admin_ids = {HISTORY_ADMIN_ID}

    session = await feed_command(dispatcher_runtime, HISTORY_ADMIN_ID, "/health extra")

    expected_texts = ["🔎 Проверяю состояние компонентов..."]
    assert sent_texts(session) == expected_texts, "progress message was not sent"


@pytest.mark.asyncio
async def test_health_reports_all_component_statuses(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.admin_ids = {HISTORY_ADMIN_ID}

    session = await feed_command(dispatcher_runtime, HISTORY_ADMIN_ID, "/health now")

    expected_texts = [
        (
            "🩺 <b>Состояние бота</b>\n\n"
            "🟢 Telegram API: Доступен\n"
            "🟢 База данных: Подключена\n"
            "🟢 Инференс: Доступен"
        )
    ]
    assert _edited_texts(session) == expected_texts, "healthy report is wrong"


@pytest.mark.asyncio
async def test_health_sends_a_progress_message_when_components_fail(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = await _feed_health_with_failures(
        access_database, dispatcher_runtime, monkeypatch
    )

    expected_texts = ["🔎 Проверяю состояние компонентов..."]
    assert sent_texts(session) == expected_texts, "progress message was not sent"


@pytest.mark.asyncio
async def test_health_reports_failed_telegram_database_and_llm(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = await _feed_health_with_failures(
        access_database, dispatcher_runtime, monkeypatch
    )

    expected_texts = [
        (
            "🩺 <b>Состояние бота</b>\n\n"
            "🔴 Telegram API: Недоступен\n"
            "🔴 База данных: Ошибка подключения\n"
            "🔴 Инференс: Недоступен"
        )
    ]
    assert _edited_texts(session) == expected_texts, "failure report is wrong"


@pytest.mark.asyncio
async def test_health_denies_user_when_admin_lookup_fails(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
    access_database.scenario.fail_admin_lookup_on = 2

    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 100,
        "/health",
    )

    expected_texts = ["⚠️ Не удалось проверить права администратора."]
    assert sent_texts(session) == expected_texts, (
        "admin lookup failure was not reported"
    )
