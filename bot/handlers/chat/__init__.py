# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Router for handling incoming chat messages.

Public names from the legacy bot.handlers.chat module are preserved for compatibility.
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
    log_incoming_message,
    logger,
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
    "log_incoming_message",
    "logger",
    "prepare_message",
    "process_chat",
    "router",
    "safe_edit",
    "split_formatted_message",
]
