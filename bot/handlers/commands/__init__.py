"""Backward-compatible command router facade.

The command registration order mirrors the former commands.py module:
history_clear, history, prompt workflow, history_limit, then unknown commands.
"""

import logging

from aiogram import Router

from bot.fsm.keys import (
    PROMPT_FLOW_KEY,
    PROMPT_STATUS_MESSAGE_KEY,
    WELCOME_MESSAGE_KEY,
    UNKNOWN_COMMAND_MESSAGE_KEY,
    UNKNOWN_COMMAND_STATUS_MESSAGE_KEY,
)
from bot.fsm.states import PromptStates
from bot.middlewares.temporary_messages import TemporaryMessagesCleanupMiddleware
from bot.handlers.history import basic as history_basic
from bot.handlers.history import limits as history_limits
from bot.handlers.prompt import handler as prompt
from bot.handlers.fallback import handler as fallback


logger = logging.getLogger("bot.handlers.commands")
router = Router()
router.include_router(history_basic.router)
router.include_router(prompt.router)
router.include_router(history_limits.router)
router.include_router(fallback.router)

# Re-export historical helper names used by existing tests and integrations.
MAX_SYSTEM_PROMPT_LENGTH = prompt.MAX_SYSTEM_PROMPT_LENGTH
MAX_DISPLAY_LENGTH = prompt.MAX_DISPLAY_LENGTH
format_prompt = prompt.format_prompt
track_message = prompt.track_message
delete_prompt_messages = prompt.delete_prompt_messages
send_prompt_status = prompt.send_prompt_status
show_prompt = prompt.show_prompt
show_history_limit = history_basic.show_history_limit
is_history_admin = history_limits.is_history_admin
cmd_history_clear = history_basic.cmd_history_clear
cmd_history = history_basic.cmd_history
cmd_prompt = prompt.cmd_prompt
cmd_prompt_set = prompt.cmd_prompt_set
save_prompt = prompt.save_prompt
reset_prompt = prompt.reset_prompt
cmd_prompt_reset = prompt.cmd_prompt_reset
cmd_cancel = prompt.cmd_cancel
cmd_history_limit = history_limits.cmd_history_limit
cmd_unknown = fallback.cmd_unknown

__all__ = [
    "router",
    "logger",
    "TemporaryMessagesCleanupMiddleware",
    "PromptStates",
    "PROMPT_FLOW_KEY",
    "PROMPT_STATUS_MESSAGE_KEY",
    "WELCOME_MESSAGE_KEY",
    "UNKNOWN_COMMAND_MESSAGE_KEY",
    "UNKNOWN_COMMAND_STATUS_MESSAGE_KEY",
    "MAX_SYSTEM_PROMPT_LENGTH",
    "MAX_DISPLAY_LENGTH",
    "format_prompt",
    "track_message",
    "delete_prompt_messages",
    "send_prompt_status",
    "show_prompt",
    "show_history_limit",
    "is_history_admin",
    "cmd_history_clear",
    "cmd_history",
    "cmd_prompt",
    "cmd_prompt_set",
    "save_prompt",
    "reset_prompt",
    "cmd_prompt_reset",
    "cmd_cancel",
    "cmd_history_limit",
    "cmd_unknown",
]
