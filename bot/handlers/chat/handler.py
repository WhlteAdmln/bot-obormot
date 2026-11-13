# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Telegram handler входящих сообщений чата."""

import asyncio
import logging

from aiogram import Router
from aiogram.types import Message

from bot.services.chat.aggregation import message_aggregator
from bot.services.chat.errors.handler import handle_chat_error
from bot.services.chat.formatting import format_roleplay, split_formatted_message
from bot.services.chat.incoming_log import log_incoming_message
from bot.services.chat.input import inspect_message, prepare_message
from bot.services.chat.locks import get_user_lock, pending_requests
from bot.services.chat.pipeline import process_chat
from bot.services.chat.reporting import safe_edit
from bot.services.chat.streaming import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
    StreamingResponder,
    deliver_final_response,
)
from bot.services.llm import llm_client
from bot.services.telegram.chat_action import keep_typing

MAX_PENDING_PER_USER = 3

router = Router()
logger = logging.getLogger("bot.handlers.chat")


@router.message()
async def handle_message(message: Message) -> None:
    """Processes an incoming chat message and streams the LLM reply."""
    log_incoming_message(message)

    info = inspect_message(message)

    if not info.has_content:
        return

    user_id = message.from_user.id

    aggregated_text = None

    # Объединяем только обычные текстовые сообщения.
    # Медиа, аудио и документы остаются без изменений.
    if (
        info.has_text
        and not info.has_media
        and not info.has_audio
        and not info.has_document
    ):
        aggregated_text = await message_aggregator.collect(message)

        # Это продолжение предыдущей части.
        # Его обработает handler первого сообщения.
        if aggregated_text is None:
            return

    if pending_requests(user_id) >= MAX_PENDING_PER_USER:
        await message.answer(
            "⏳ Я ещё обрабатываю твои предыдущие сообщения. Подожди немного."
        )
        return

    async with get_user_lock(user_id):
        responder = StreamingResponder(
            message=message,
            user_id=user_id,
            count_text_tokens=llm_client.count_text_tokens,
            safe_edit=safe_edit,
            formatter=format_roleplay,
            splitter=split_formatted_message,
        )
        typing_task = asyncio.create_task(keep_typing(message))

        try:
            # Подготавливаем текст, аудио, изображения и документы.
            prepared = await prepare_message(
                message,
                info,
                text_override=aggregated_text,
            )

            # Получаем ответ от LLM.
            # Полный ответ сохраняется в БД внутри process_chat.
            response = await process_chat(
                user_id=user_id,
                user_content=prepared.user_content,
                saved_user_text=prepared.saved_user_text,
                media=prepared.image_bytes,
                on_update=responder.on_update,
            )

            await deliver_final_response(
                message=message,
                response=response,
                status=responder.status,
                safe_edit=safe_edit,
                formatter=format_roleplay,
                splitter=split_formatted_message,
                max_message_length=MAX_MESSAGE_LENGTH,
                user_id=user_id,
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
    "llm_client",
    "log_incoming_message",
    "logger",
    "message_aggregator",
    "prepare_message",
    "process_chat",
    "router",
    "safe_edit",
    "split_formatted_message",
]
