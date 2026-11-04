"""Совместимый фасад старого API подготовки входящих сообщений."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.services.chat.input.inspection import (
    inspect_message as _inspect_message,
)
from bot.services.chat.input.models import MessageInfo, PreparedMessage
from bot.services.chat.input.prepare import (
    logger,
    prepare_message as _prepare_message,
)

if TYPE_CHECKING:
    from aiogram.types import Message


def inspect_message(message: Message) -> MessageInfo:
    """Определяет типы содержимого входящего сообщения."""

    return _inspect_message(message)


async def prepare_message(
    message: Message,
    info: MessageInfo,
    text_override: str | None = None,
) -> PreparedMessage:
    """Скачивает и обрабатывает входящие данные."""

    return await _prepare_message(message, info, text_override)


__all__ = [
    "MessageInfo",
    "PreparedMessage",
    "inspect_message",
    "logger",
    "prepare_message",
]
