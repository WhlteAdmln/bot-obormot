"""Сервис подготовки входящих сообщений для chat pipeline."""

from bot.services.chat.input.inspection import inspect_message as _inspect_message
from bot.services.chat.input.models import MessageInfo, PreparedMessage
from bot.services.chat.input.prepare import logger, prepare_message


def inspect_message(message):
    """Публичная функция определения сообщения с прежней сигнатурой."""
    return _inspect_message(message)


__all__ = [
    "MessageInfo",
    "PreparedMessage",
    "inspect_message",
    "logger",
    "prepare_message",
]
