# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""System-prompt configuration commands."""

from bot_obormot.handlers.prompt.handler import (
    MAX_DISPLAY_LENGTH,
    MAX_SYSTEM_PROMPT_LENGTH,
    cmd_cancel,
    cmd_prompt,
    cmd_prompt_reset,
    cmd_prompt_set,
    create_router,
    delete_prompt_messages,
    format_prompt,
    reset_prompt,
    save_prompt,
    send_prompt_status,
    show_prompt,
    track_message,
)

__all__ = [
    "MAX_DISPLAY_LENGTH",
    "MAX_SYSTEM_PROMPT_LENGTH",
    "cmd_cancel",
    "cmd_prompt",
    "cmd_prompt_reset",
    "cmd_prompt_set",
    "create_router",
    "delete_prompt_messages",
    "format_prompt",
    "reset_prompt",
    "save_prompt",
    "send_prompt_status",
    "show_prompt",
    "track_message",
]
