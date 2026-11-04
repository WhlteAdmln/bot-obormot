"""System-prompt configuration commands."""

from bot.handlers.prompt.handler import (
    router,
    MAX_SYSTEM_PROMPT_LENGTH,
    MAX_DISPLAY_LENGTH,
    format_prompt,
    track_message,
    delete_prompt_messages,
    send_prompt_status,
    show_prompt,
    cmd_prompt,
    cmd_prompt_set,
    save_prompt,
    reset_prompt,
    cmd_prompt_reset,
    cmd_cancel,
)

__all__ = [
    "router",
    "MAX_SYSTEM_PROMPT_LENGTH",
    "MAX_DISPLAY_LENGTH",
    "format_prompt",
    "track_message",
    "delete_prompt_messages",
    "send_prompt_status",
    "show_prompt",
    "cmd_prompt",
    "cmd_prompt_set",
    "save_prompt",
    "reset_prompt",
    "cmd_prompt_reset",
    "cmd_cancel",
]
