"""Роутер обработки входящих сообщений чата.

Публичные имена старого модуля bot.handlers.chat сохранены для совместимости.
"""

from bot.handlers.chat.handler import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
    format_roleplay,
    get_user_lock,
    handle_chat_error,
    handle_message,
    inspect_message,
    keep_typing,
    llm_client,
    log_incoming_message,
    logger,
    message_aggregator,
    prepare_message,
    process_chat,
    router,
    safe_edit,
    split_formatted_message,
)

__all__ = [
    "MAX_MESSAGE_LENGTH",
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
