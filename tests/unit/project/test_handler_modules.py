# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for project handler modules."""

from bot_obormot.fsm.keys import PROMPT_FLOW_KEY, WELCOME_MESSAGE_KEY
from bot_obormot.fsm.states import PromptStates
from bot_obormot.handlers.admin import handler as admin_handler
from bot_obormot.handlers.history import basic as history_basic
from bot_obormot.handlers.history import limits as history_limits
from bot_obormot.handlers.start import handler as start_handler
from bot_obormot.middlewares import access as access_middleware
from bot_obormot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)


def test_fsm_and_middleware_imports_use_canonical_modules() -> None:
    """Fsm and middleware imports use canonical modules."""
    assert PromptStates.waiting_for_prompt is not None
    assert PROMPT_FLOW_KEY == "prompt_flow_message_ids"
    assert WELCOME_MESSAGE_KEY == "start_welcome_message_id"
    assert (
        TemporaryMessagesCleanupMiddleware.__module__
        == "bot_obormot.middlewares.temporary_messages.middleware"
    )


def test_settings_migrated_modules_do_not_import_legacy_config() -> None:
    """Migrated handlers and middleware do not import the legacy config proxy."""
    modules = (
        admin_handler,
        history_basic,
        history_limits,
        start_handler,
        access_middleware,
    )

    assert all("config" not in vars(module) for module in modules)
