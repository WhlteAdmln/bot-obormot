# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""In-process end-to-end chat flows."""

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText, SendChatAction, SendMessage

import bot.services.chat.pipeline as chat_pipeline
from bot.app.routers import configure_dispatcher
from bot.config import config
from bot.middlewares import access as access_middleware
from bot.services.chat.formatting import format_roleplay
from bot.services.database import Database
from bot.services.llm import llm_client
from tests.support.fake_llm import FakeLLM, FakeLLMOptions
from tests.support.telegram import FakeTelegramSession, make_message, make_update


async def _reset_llm_client() -> None:
    """Close the LLM session and clear cached server metadata."""
    await llm_client.close()
    llm_client._context_size = None
    llm_client._token_counting_mode = None


@pytest.mark.asyncio
async def test_text_message_streams_answer_and_persists_exchange(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process a text message through Dispatcher, LLM and SQLite."""
    user_id = 712345678
    user_text = "Объясни, пожалуйста, как работает SQLite."
    first_chunk = " ".join(["streamed"] * 180) + " "
    response = f"{first_chunk}complete"

    await _reset_llm_client()

    try:
        async with FakeLLM(
            options=FakeLLMOptions(chunks=(first_chunk, "complete")),
        ) as llm_server:
            monkeypatch.setattr(
                config,
                "LLM_BASE_URL",
                f"{llm_server.base_url.rstrip('/')}/v1",
            )
            monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
            monkeypatch.setattr(config, "LLM_MODEL", "test-model")
            monkeypatch.setattr(config, "LLM_CONTEXT_SIZE", None)
            monkeypatch.setattr(config, "LLM_TOKEN_COUNTING", "auto")
            monkeypatch.setattr(config, "ALLOW_ALL_USERS", True)
            monkeypatch.setattr(config, "ALLOWED_USERS", set())
            monkeypatch.setattr(access_middleware, "db", test_db)
            monkeypatch.setattr(chat_pipeline, "db", test_db)

            telegram_session = FakeTelegramSession(
                {
                    SendChatAction: True,
                    SendMessage: make_message(
                        message_id=900,
                        chat_id=user_id,
                        user_id=900,
                        text=None,
                    ),
                    EditMessageText: make_message(
                        message_id=900,
                        chat_id=user_id,
                        user_id=900,
                        text=None,
                    ),
                }
            )
            bot = Bot(token=config.BOT_TOKEN, session=telegram_session)
            dispatcher = configure_dispatcher(Dispatcher(storage=MemoryStorage()))

            try:
                await dispatcher.feed_update(
                    bot,
                    make_update(
                        message=make_message(
                            user_id=user_id,
                            chat_id=user_id,
                            text=user_text,
                        )
                    ),
                )
            finally:
                await bot.session.close()

            sent_messages = [
                request
                for request in telegram_session.requests
                if isinstance(request, SendMessage)
            ]
            edited_texts = [
                request.text
                for request in telegram_session.requests
                if isinstance(request, EditMessageText) and request.text is not None
            ]

            assert llm_server.stream_started.is_set()
            assert len(sent_messages) == 1
            assert sent_messages[0].text is not None
            assert "streamed" in sent_messages[0].text
            assert edited_texts
            assert edited_texts[-1] == format_roleplay(response)

            history = await test_db.get_history(user_id)
            assert [(item["role"], item["content"]) for item in history] == [
                ("user", user_text),
                ("assistant", response),
            ]
    finally:
        await _reset_llm_client()
