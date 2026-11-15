# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Сервис подготовки входящих сообщений для chat pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.services.chat.input.inspection import inspect_message as _inspect_message
from bot.services.chat.input.models import MessageInfo, PreparedMessage
from bot.services.chat.input.prepare import logger, prepare_message

if TYPE_CHECKING:
    from aiogram.types import Message


def inspect_message(message: Message) -> MessageInfo:
    """Публичная функция определения сообщения с прежней сигнатурой."""
    return _inspect_message(message)


__all__ = [
    "MessageInfo",
    "PreparedMessage",
    "inspect_message",
    "logger",
    "prepare_message",
]
