# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake aiogram session and Telegram object builders."""

import pytest
from aiogram import Bot
from aiogram.methods import SendMessage

from tests.support.settings import make_settings
from tests.support.telegram import FakeTelegramSession, make_message, make_update


@pytest.mark.asyncio
async def test_fake_telegram_session_records_requests_and_streams_content() -> None:
    """Exercise a real aiogram Bot against the canned fake session."""
    response = make_message(message_id=7, chat_id=42, text="Telegram reply")
    session = FakeTelegramSession(
        {SendMessage: response},
        stream_data=b"file-data",
    )
    bot = Bot(token=make_settings().BOT_TOKEN, session=session)

    try:
        result = await bot.send_message(chat_id=42, text="Hello")
        assert result == response
        assert len(session.requests) == 1
        request = session.requests[0]
        assert isinstance(request, SendMessage)
        assert request.chat_id == 42
        assert request.text == "Hello"

        chunks = [
            chunk
            async for chunk in session.stream_content(
                "https://telegram.test/file",
                chunk_size=4,
            )
        ]
        assert chunks == [b"file", b"-dat", b"a"]
        assert session.streamed_urls == ["https://telegram.test/file"]
    finally:
        await bot.session.close()

    assert session.closed

    message = make_message(
        message_id=3,
        chat_id=11,
        user_id=12,
        text="Test update",
    )
    update = make_update(update_id=17, message=message)
    assert update.update_id == 17
    assert update.message == message
