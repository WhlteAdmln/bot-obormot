# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Telegram handler for incoming chat messages."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

from aiogram import Router

from bot_obormot.handlers.chat.texts import PENDING_REQUESTS_MESSAGE
from bot_obormot.services.chat.errors.handler import handle_chat_error
from bot_obormot.services.chat.formatting import (
    prepare_response,
    split_formatted_message,
)
from bot_obormot.services.chat.incoming_log import log_incoming_message
from bot_obormot.services.chat.input import inspect_message, prepare_message
from bot_obormot.services.chat.pipeline import (
    ChatPipelineDependencies,
    process_chat,
)
from bot_obormot.services.chat.reply import ReplyTarget
from bot_obormot.services.chat.reporting import safe_edit
from bot_obormot.services.chat.streaming import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
    StreamingResponder,
    deliver_final_response,
)
from bot_obormot.services.chat.streaming.delivery import DeliveryOptions
from bot_obormot.services.telegram.chat_action import keep_typing
from bot_obormot.settings import get_settings

if TYPE_CHECKING:
    from aiogram.types import Message

    from bot_obormot.services.chat.aggregation import MessageAggregator
    from bot_obormot.services.chat.input import MessageInfo
    from bot_obormot.services.chat.locks import UserLocks
    from bot_obormot.services.database import Database
    from bot_obormot.services.llm.client import LLMClient
    from bot_obormot.services.media import MediaSlots
    from bot_obormot.services.telegram import TelegramDownloader
    from bot_obormot.settings import Settings

MAX_PENDING_PER_USER = 3

logger = logging.getLogger("bot_obormot.handlers.chat")


@dataclass(frozen=True)
class ChatRuntime:
    """Objects that live as long as one running bot and serve the chat handler."""

    message_aggregator: MessageAggregator
    user_locks: UserLocks
    downloader: TelegramDownloader
    media_slots: MediaSlots


@dataclass(frozen=True)
class _ChatTurn:
    """Everything needed to answer one request, which may combine messages."""

    message: Message
    info: MessageInfo
    aggregated_text: str | None
    settings: Settings
    user_id: int
    reply_to: ReplyTarget
    dependencies: ChatPipelineDependencies


async def _answer_turn(
    turn: _ChatTurn,
    responder: StreamingResponder,
    runtime: ChatRuntime,
) -> None:
    """Prepare the input, get the LLM reply, and deliver the final response."""
    # Prepare text, audio, images, and documents.
    prepared = await prepare_message(
        turn.message,
        turn.info,
        text_override=turn.aggregated_text,
        settings=turn.settings,
        downloader=runtime.downloader,
        media_slots=runtime.media_slots,
    )

    # Get the response from the LLM.
    # The full response is saved to the database inside process_chat.
    response = await process_chat(
        user_id=turn.user_id,
        user_content=prepared.user_content,
        saved_user_text=prepared.saved_user_text,
        media=prepared.image_bytes,
        on_update=responder.on_update,
        dependencies=turn.dependencies,
    )

    await deliver_final_response(
        message=turn.message,
        response=response,
        status=responder.status,
        safe_edit=safe_edit,
        options=DeliveryOptions(
            preparer=prepare_response,
            max_message_length=MAX_MESSAGE_LENGTH,
            user_id=turn.user_id,
            reply_to=turn.reply_to,
        ),
    )


async def handle_message(
    message: Message,
    settings: Settings | None = None,
    *,
    llm_client: LLMClient,
    database: Database,
    chat_runtime: ChatRuntime,
) -> None:
    """Processes an incoming chat message and streams the LLM reply."""
    if settings is None:
        settings = get_settings()

    log_incoming_message(message)

    info = inspect_message(message)

    if not info.has_content:
        return

    if message.from_user is None:
        return

    user_id = message.from_user.id

    aggregated_text: str | None = None

    # Aggregate only ordinary text messages.
    # Media, audio, and documents remain unchanged.
    if (
        info.has_text
        and not info.has_media
        and not info.has_audio
        and not info.has_document
    ):
        aggregated_text = await chat_runtime.message_aggregator.collect(message)

        # This is a continuation of the previous part.
        # It will be handled by the handler for the first message.
        if aggregated_text is None:
            return

    if chat_runtime.user_locks.pending(user_id) >= MAX_PENDING_PER_USER:
        await message.answer(PENDING_REQUESTS_MESSAGE)
        return

    # The response is linked to the last message of the request: this is the
    # message itself, or the last one of several combined messages.
    reply_to = ReplyTarget.from_message(
        getattr(aggregated_text, "last_message", None) or message
    )
    logger.debug(
        "Reply target for user_id=%s: chat_id=%s, message_id=%s",
        user_id,
        reply_to.chat_id,
        reply_to.message_id,
    )

    async with chat_runtime.user_locks.hold(user_id):
        responder = StreamingResponder(
            message=message,
            user_id=user_id,
            count_text_tokens=llm_client.count_text_tokens,
            safe_edit=safe_edit,
            reply_to=reply_to,
        )
        typing_task = asyncio.create_task(keep_typing(message))

        turn = _ChatTurn(
            message=message,
            info=info,
            aggregated_text=aggregated_text,
            settings=settings,
            user_id=user_id,
            reply_to=reply_to,
            dependencies=ChatPipelineDependencies(
                llm_client=llm_client,
                database=database,
            ),
        )

        try:
            await _answer_turn(turn, responder, chat_runtime)

        except asyncio.CancelledError:
            logger.info(
                "Message processing cancelled for user_id=%s",
                user_id,
            )
            await responder.cancel()
            raise

        except Exception as error:  # noqa: BLE001 - logged by handle_chat_error
            await handle_chat_error(
                message=message,
                status=responder.status,
                user_id=user_id,
                error=error,
            )

        finally:
            if not typing_task.done():
                typing_task.cancel()

            await asyncio.gather(
                typing_task,
                return_exceptions=True,
            )


def create_router(runtime: ChatRuntime) -> Router:
    """Build a router whose chat message handler serves one bot's runtime."""
    router = Router()
    router.message.register(partial(handle_message, chat_runtime=runtime))
    return router


__all__ = [
    "MAX_MESSAGE_LENGTH",
    "MAX_PENDING_PER_USER",
    "STREAM_TOKEN_THRESHOLD",
    "STREAM_UPDATE_INTERVAL",
    "ChatRuntime",
    "create_router",
    "handle_chat_error",
    "handle_message",
    "inspect_message",
    "keep_typing",
    "log_incoming_message",
    "logger",
    "prepare_message",
    "prepare_response",
    "process_chat",
    "safe_edit",
    "split_formatted_message",
]
