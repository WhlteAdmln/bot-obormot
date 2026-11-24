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


@pytest.mark.asyncio
async def test_health_reports_all_component_statuses(
    access_database: AccessDatabase,
    dispatcher_runtime: tuple[Dispatcher, Bot, FakeTelegramSession],
) -> None:
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

    async def fail_get_me(_bot: Bot) -> User:
        msg = "Telegram unavailable"
        raise RuntimeError(msg)

    dispatcher, bot, session = dispatcher_runtime
    access_database.scenario.failed_operation = "health_check"
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
    access_database.scenario.fail_admin_lookup_on = 2

    session = await feed_command(
        dispatcher_runtime,
        HISTORY_USER_ID + 100,
        "/health",
    )

    assert sent_texts(session) == ["⚠️ Не удалось проверить права администратора."]
