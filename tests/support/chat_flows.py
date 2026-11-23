# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build Telegram updates and dispatchers for in-process chat flows."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import EditMessageText, GetFile, SendChatAction, SendMessage
from aiogram.types import Document, Message, Voice
from aiogram.types import File as TelegramFile

from bot_obormot.app.routers import configure_dispatcher
from bot_obormot.services.database import Database
from bot_obormot.services.llm import LLMClient
from bot_obormot.settings import Settings
from tests.support.dispatcher import detach_router
from tests.support.settings import make_settings
from tests.support.telegram import FakeTelegramSession, make_message


def create_flow_dispatcher(
    settings: Settings,
    database: Database,
) -> Dispatcher:
    """Create a dispatcher with isolated application dependencies."""
    client = LLMClient(settings)
    return configure_dispatcher(
        Dispatcher(storage=MemoryStorage()),
        settings,
        client,
        database=database,
    )


async def close_flow_llm_client(dispatcher: Dispatcher | None) -> None:
    """Close the LLM client owned by an integration flow."""
    if dispatcher is not None:
        await dispatcher.workflow_data["llm_client"].close()


def configure_llm_flow(llm_base_url: str, **overrides: object) -> Settings:
    """Build settings for the fake LLM server and apply them to the LLM client."""
    options: dict[str, object] = {
        "LLM_BASE_URL": f"{llm_base_url.rstrip('/')}/v1",
        "LLM_API_KEY": "test-key",
        "LLM_MODEL": "test-model",
        "LLM_CONTEXT_SIZE": None,
        "LLM_TOKEN_COUNTING": "auto",
        "ALLOW_ALL_USERS": True,
        "ALLOWED_USERS": set(),
    }
    options.update(overrides)
    return make_settings(**options)


def release_dispatcher(dispatcher: Dispatcher) -> None:
    """Detach shared application routers after an integration flow."""
    for router in dispatcher.sub_routers:
        detach_router(router)
    dispatcher.sub_routers.clear()


def make_private_message(user_id: int, **update: object) -> Message:
    """Build a private message from the user with the given content fields."""
    return make_message(
        user_id=user_id,
        chat_id=user_id,
        text=None,
    ).model_copy(update=update)


def make_voice_message(user_id: int, audio_size: int) -> Message:
    """Build a deterministic voice message."""
    return make_private_message(
        user_id,
        voice=Voice(
            file_id="voice-file-id",
            file_unique_id="voice-file-unique-id",
            duration=2,
            mime_type="audio/ogg",
            file_size=audio_size,
        ),
    )


def make_voice_telegram_session(
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


def make_document_message(user_id: int, document_size: int) -> Message:
    """Build a deterministic PDF message."""
    return make_private_message(
        user_id,
        document=Document(
            file_id="document-file-id",
            file_unique_id="document-file-unique-id",
            file_name="report.pdf",
            mime_type="application/pdf",
            file_size=document_size,
        ),
    )


def make_document_telegram_session(
    user_id: int,
    document_data: bytes,
) -> FakeTelegramSession:
    """Create fake Telegram responses for PDF download and replies."""
    return FakeTelegramSession(
        {
            GetFile: TelegramFile(
                file_id="document-file-id",
                file_unique_id="document-file-unique-id",
                file_size=len(document_data),
                file_path="documents/report.pdf",
            ),
            SendChatAction: True,
            SendMessage: make_message(
                message_id=902,
                chat_id=user_id,
                user_id=902,
                text=None,
            ),
            EditMessageText: make_message(
                message_id=902,
                chat_id=user_id,
                user_id=902,
                text=None,
            ),
        },
        stream_data=document_data,
    )


def configure_voice_flow(
    *,
    llm_base_url: str,
    audiodoc_base_url: str,
) -> Settings:
    """Configure real clients to use local fake backend servers."""
    return configure_llm_flow(
        llm_base_url,
        AUDIODOC_URL=audiodoc_base_url.rstrip("/"),
        AUDIODOC_AUDIO_KEY="whisper-test-key",
    )


def configure_document_flow(
    *,
    llm_base_url: str,
    audiodoc_base_url: str,
) -> Settings:
    """Configure real clients to use local fake backend servers."""
    return configure_llm_flow(
        llm_base_url,
        AUDIODOC_URL=audiodoc_base_url.rstrip("/"),
        AUDIODOC_DOCUMENT_KEY="document-test-key",
    )


@asynccontextmanager
async def open_flow(
    settings: Settings,
    database: Database,
    session: FakeTelegramSession,
) -> AsyncIterator[tuple[Bot, Dispatcher]]:
    """Yield a bot and a dispatcher and release them when the flow ends."""
    bot = Bot(token=settings.BOT_TOKEN, session=session)
    dispatcher = create_flow_dispatcher(settings, database)
    try:
        yield bot, dispatcher
    finally:
        await bot.session.close()
        release_dispatcher(dispatcher)
        await close_flow_llm_client(dispatcher)
