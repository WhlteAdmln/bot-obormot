# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake aiogram session and Telegram object builders."""

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.types import Message

from tests.support.settings import make_settings
from tests.support.telegram import FakeTelegramSession, make_message, make_update


async def _send(session: FakeTelegramSession, chat_id: int, text: str) -> Message:
    async with Bot(token=make_settings().BOT_TOKEN, session=session) as bot:
        return await bot.send_message(chat_id=chat_id, text=text)


async def _stream(
    session: FakeTelegramSession, url: str, chunk_size: int
) -> list[bytes]:
    return [chunk async for chunk in session.stream_content(url, chunk_size=chunk_size)]


@pytest.mark.asyncio
async def test_fake_telegram_session_returns_the_configured_response() -> None:
    response = make_message(message_id=7, chat_id=42, text="Telegram reply")
    session = FakeTelegramSession({SendMessage: response})

    result = await _send(session, 42, "Hello")

    assert result == response, "the session returned another response"


@pytest.mark.asyncio
async def test_fake_telegram_session_records_the_sent_request() -> None:
    chat_id = -100555
    text = "Привет, чат"
    response = make_message(message_id=8, chat_id=chat_id, text="Ответ")
    session = FakeTelegramSession({SendMessage: response})

    await _send(session, chat_id, text)

    recorded = [
        (
            type(request),
            getattr(request, "chat_id", None),
            getattr(request, "text", None),
        )
        for request in session.requests
    ]
    expected = [(SendMessage, chat_id, text)]
    assert recorded == expected, "the session recorded other requests"


@pytest.mark.asyncio
async def test_fake_telegram_session_streams_content_in_chunks() -> None:
    session = FakeTelegramSession({}, stream_data=b"file-data")

    chunks = await _stream(session, "https://telegram.test/file", 4)

    expected = [b"file", b"-dat", b"a"]
    assert chunks == expected, "the streamed chunks differ"


@pytest.mark.asyncio
async def test_fake_telegram_session_records_streamed_urls() -> None:
    url = "https://telegram.test/documents/file_12.pdf"
    session = FakeTelegramSession({}, stream_data=b"%PDF-1.7")

    await _stream(session, url, 3)

    expected = [url]
    assert session.streamed_urls == expected, "the streamed urls differ"


@pytest.mark.asyncio
async def test_fake_telegram_session_is_closed_with_the_bot() -> None:
    response = make_message(message_id=9, chat_id=77, text="Закрыто")
    session = FakeTelegramSession({SendMessage: response})

    await _send(session, 77, "Пока")

    assert session.closed is True, "the session stayed open after the bot closed"


def test_make_update_keeps_the_update_id() -> None:
    message = make_message(message_id=3, chat_id=11, user_id=12, text="Test update")
    update_id = 17

    update = make_update(update_id=update_id, message=message)

    assert update.update_id == update_id, "the update id differs"


def test_make_update_wraps_the_message() -> None:
    message = make_message(message_id=5, chat_id=-31, user_id=64, text="Обновление")

    update = make_update(update_id=2024, message=message)

    assert update.message == message, "the update wraps another message"
