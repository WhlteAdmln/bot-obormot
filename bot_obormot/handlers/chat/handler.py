# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Telegram handler for incoming chat messages."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from aiogram import Router

from bot_obormot.handlers.chat.texts import PENDING_REQUESTS_MESSAGE
from bot_obormot.services.chat.errors.handler import handle_chat_error
from bot_obormot.services.chat.formatting import (
    format_roleplay,
    split_formatted_message,
)
from bot_obormot.services.chat.incoming_log import log_incoming_message
from bot_obormot.services.chat.input import inspect_message, prepare_message
from bot_obormot.services.chat.locks import get_user_lock, pending_requests
from bot_obormot.services.chat.pipeline import (
    ChatPipelineDependencies,
    process_chat,
)
from bot_obormot.services.chat.reporting import safe_edit
from bot_obormot.services.chat.streaming import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
    StreamingResponder,
    deliver_final_response,
)
from bot_obormot.services.chat.streaming.delivery import DeliveryOptions
from bot_obormot.services.chat.streaming.responder import StreamingResponderOptions
from bot_obormot.services.telegram.chat_action import keep_typing
from bot_obormot.settings import get_settings

if TYPE_CHECKING:
    from aiogram.types import Message

    from bot_obormot.services.chat.aggregation import MessageAggregator
    from bot_obormot.services.database import Database
    from bot_obormot.services.llm.client import LLMClient
    from bot_obormot.settings import Settings

MAX_PENDING_PER_USER = 3

router = Router()
logger = logging.getLogger("bot_obormot.handlers.chat")


@router.message()
async def handle_message(
    message: Message,
    settings: Settings | None = None,
    *,
    llm_client: LLMClient,
    message_aggregator: MessageAggregator,
    database: Database,
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
        aggregated_text = await message_aggregator.collect(message)

        # This is a continuation of the previous part.
        # It will be handled by the handler for the first message.
        if aggregated_text is None:
            return

    if pending_requests(user_id) >= MAX_PENDING_PER_USER:
        await message.answer(PENDING_REQUESTS_MESSAGE)
        return

    async with get_user_lock(user_id):
        responder = StreamingResponder(
            message=message,
            user_id=user_id,
            count_text_tokens=llm_client.count_text_tokens,
            safe_edit=safe_edit,
            options=StreamingResponderOptions(
                formatter=format_roleplay,
                splitter=split_formatted_message,
            ),
        )
        typing_task = asyncio.create_task(keep_typing(message))

        try:
            # Prepare text, audio, images, and documents.
            prepared = await prepare_message(
                message,
                info,
                text_override=aggregated_text,
                settings=settings,
            )

            # Get the response from the LLM.
            # The full response is saved to the database inside process_chat.
            response = await process_chat(
                user_id=user_id,
                user_content=prepared.user_content,
                saved_user_text=prepared.saved_user_text,
                media=prepared.image_bytes,
                on_update=responder.on_update,
                dependencies=ChatPipelineDependencies(
                    llm_client=llm_client,
                    database=database,
                ),
            )

            await deliver_final_response(
                message=message,
                response=response,
                status=responder.status,
                safe_edit=safe_edit,
                options=DeliveryOptions(
                    formatter=format_roleplay,
                    splitter=split_formatted_message,
                    max_message_length=MAX_MESSAGE_LENGTH,
                    user_id=user_id,
                ),
            )

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


__all__ = [
    "MAX_MESSAGE_LENGTH",
    "MAX_PENDING_PER_USER",
    "STREAM_TOKEN_THRESHOLD",
    "STREAM_UPDATE_INTERVAL",
    "format_roleplay",
    "get_user_lock",
    "handle_chat_error",
    "handle_message",
    "inspect_message",
    "keep_typing",
    "log_incoming_message",
    "logger",
    "prepare_message",
    "process_chat",
    "router",
    "safe_edit",
    "split_formatted_message",
]
