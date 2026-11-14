# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Финальная доставка полного ответа Telegram-пользователю."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram.types import Message

from bot.services.chat.formatting import format_roleplay, split_formatted_message
from bot.services.chat.streaming.settings import MAX_MESSAGE_LENGTH

logger = logging.getLogger("bot.handlers.chat")

Formatter = Callable[[str], str]
Splitter = Callable[..., list[str]]
SafeEdit = Callable[[Any, str], Awaitable[None]]


@dataclass(frozen=True)
class DeliveryOptions:
    """Configuration for final response formatting and delivery."""

    formatter: Formatter = format_roleplay
    splitter: Splitter = split_formatted_message
    max_message_length: int = MAX_MESSAGE_LENGTH
    user_id: int | None = None


_DEFAULT_DELIVERY_OPTIONS: DeliveryOptions = DeliveryOptions()


async def deliver_final_response(
    message: Message,
    response: str,
    status: Message | None,
    safe_edit: SafeEdit,
    *,
    options: DeliveryOptions = _DEFAULT_DELIVERY_OPTIONS,
) -> None:
    """Форматирует и доставляет итоговый ответ с прежним fallback-поведением."""
    formatted_response = options.formatter(response)
    response_chunks = options.splitter(
        formatted_response,
        max_length=options.max_message_length,
    )

    if not response_chunks:
        return

    # Если streaming не запускался, отправляем ответ целиком.
    if status is None:
        for chunk in response_chunks:
            await message.answer(
                chunk,
                parse_mode="HTML",
            )
        return

    # Обновляем последнее потоковое сообщение окончательным текстом.
    try:
        await safe_edit(
            status,
            response_chunks[0],
        )

        # Остальные части отправляем отдельными сообщениями.
        for chunk in response_chunks[1:]:
            await message.answer(
                chunk,
                parse_mode="HTML",
            )

    except Exception:
        logger.warning(
            "Could not finalize streaming response for user_id=%s. "
            "Sending complete response again.",
            options.user_id,
            exc_info=True,
        )

        # Резервный вариант: отправляем полный ответ.
        for chunk in response_chunks:
            await message.answer(
                chunk,
                parse_mode="HTML",
            )


__all__ = ["DeliveryOptions", "deliver_final_response"]
