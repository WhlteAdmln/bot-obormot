# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""In-process end-to-end chat flows."""

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText, GetFile, SendChatAction, SendMessage
from aiogram.types import File as TelegramFile
from aiogram.types import Message, Voice

import bot.services.chat.pipeline as chat_pipeline
from bot.app.routers import configure_dispatcher
from bot.config import config
from bot.middlewares import access as access_middleware
from bot.services.chat.formatting import format_roleplay
from bot.services.database import Database
from bot.services.llm import llm_client
from tests.support.fake_audiodoc import FakeAudiodoc
from tests.support.fake_llm import FakeLLM, FakeLLMOptions
from tests.support.telegram import FakeTelegramSession, make_message, make_update


async def _reset_llm_client() -> None:
    """Close the LLM session and clear cached server metadata."""
    await llm_client.close()
    llm_client._context_size = None
    llm_client._token_counting_mode = None


def _make_voice_message(user_id: int, audio_size: int) -> Message:
    """Build a deterministic voice message."""
    return make_message(
        user_id=user_id,
        chat_id=user_id,
        text=None,
    ).model_copy(
        update={
            "voice": Voice(
                file_id="voice-file-id",
                file_unique_id="voice-file-unique-id",
                duration=2,
                mime_type="audio/ogg",
                file_size=audio_size,
            )
        }
    )


def _make_voice_telegram_session(
    user_id: int,
    audio_data: bytes,
) -> FakeTelegramSession:
    """Create fake Telegram responses for voice download and replies."""
    return FakeTelegramSession(
        {
            GetFile: TelegramFile(
                file_id="voice-file-id",
                file_unique_id="voice-file-unique-id",
                file_size=len(audio_data),
                file_path="voice/test.ogg",
            ),
            SendChatAction: True,
            SendMessage: make_message(
                message_id=901,
                chat_id=user_id,
                user_id=901,
                text=None,
            ),
            EditMessageText: make_message(
                message_id=901,
                chat_id=user_id,
                user_id=901,
                text=None,
            ),
        },
        stream_data=audio_data,
    )


def _configure_voice_flow(
    monkeypatch: pytest.MonkeyPatch,
    test_db: Database,
    *,
    llm_base_url: str,
    audiodoc_base_url: str,
) -> None:
    """Configure real clients to use local fake backend servers."""
    monkeypatch.setattr(
        config,
        "LLM_BASE_URL",
        f"{llm_base_url.rstrip('/')}/v1",
    )
    monkeypatch.setattr(config, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(config, "LLM_CONTEXT_SIZE", None)
    monkeypatch.setattr(config, "LLM_TOKEN_COUNTING", "auto")
    monkeypatch.setattr(config, "ALLOW_ALL_USERS", True)
    monkeypatch.setattr(config, "ALLOWED_USERS", set())
    monkeypatch.setattr(
        config,
        "WHISPER_API_URL",
        f"{audiodoc_base_url.rstrip('/')}/transcribe",
    )
    monkeypatch.setattr(config, "WHISPER_API_KEY", "whisper-test-key")
    monkeypatch.setattr(access_middleware, "db", test_db)
    monkeypatch.setattr(chat_pipeline, "db", test_db)


def _assert_voice_delivery(
    telegram_session: FakeTelegramSession,
    llm_server: FakeLLM,
    response: str,
) -> None:
    """Verify Telegram download and streamed response delivery."""
    file_requests = [
        request for request in telegram_session.requests if isinstance(request, GetFile)
    ]
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

    assert len(file_requests) == 1
    assert telegram_session.streamed_urls
    assert telegram_session.streamed_urls[0].endswith("/voice/test.ogg")
    assert llm_server.stream_started.is_set()
    assert len(sent_messages) == 1
    assert edited_texts
    assert edited_texts[-1] == format_roleplay(response)


async def _assert_voice_history(
    test_db: Database,
    user_id: int,
    response: str,
) -> None:
    """Verify that transcription and assistant response were persisted."""
    history = await test_db.get_history(user_id)

    assert len(history) == 2
    assert "Recognized speech." in history[0]["content"]
    assert history[1]["content"] == response


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


@pytest.mark.asyncio
async def test_voice_message_is_transcribed_answered_and_persisted(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process a voice message through Telegram, audiodoc, LLM and SQLite."""
    user_id = 712345679
    first_chunk = " ".join(["streamed"] * 180) + " "
    response = f"{first_chunk}complete"
    audio_data = b"OggS-fake-voice-data"

    await _reset_llm_client()

    try:
        async with (
            FakeAudiodoc() as audiodoc_server,
            FakeLLM(
                options=FakeLLMOptions(chunks=(first_chunk, "complete")),
            ) as llm_server,
        ):
            _configure_voice_flow(
                monkeypatch,
                test_db,
                llm_base_url=llm_server.base_url,
                audiodoc_base_url=audiodoc_server.base_url,
            )

            telegram_session = _make_voice_telegram_session(user_id, audio_data)
            bot = Bot(token=config.BOT_TOKEN, session=telegram_session)
            dispatcher = configure_dispatcher(Dispatcher(storage=MemoryStorage()))
            voice_message = _make_voice_message(user_id, len(audio_data))

            try:
                await dispatcher.feed_update(
                    bot,
                    make_update(message=voice_message),
                )
            finally:
                await bot.session.close()

            _assert_voice_delivery(telegram_session, llm_server, response)
            await _assert_voice_history(test_db, user_id, response)
    finally:
        await _reset_llm_client()
