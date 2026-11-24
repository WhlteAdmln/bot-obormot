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
    assert PromptStates.waiting_for_prompt is not None
    expected_prompt_flow_key = "prompt_flow_message_ids"
    assert expected_prompt_flow_key == PROMPT_FLOW_KEY
    expected_welcome_message_key = "start_welcome_message_id"
    assert expected_welcome_message_key == WELCOME_MESSAGE_KEY
    expected_module = "bot_obormot.middlewares.temporary_messages.middleware"
    assert TemporaryMessagesCleanupMiddleware.__module__ == expected_module


def test_settings_migrated_modules_do_not_import_legacy_config() -> None:
    modules = (
        admin_handler,
        history_basic,
        history_limits,
        start_handler,
        access_middleware,
    )

    legacy_module = "config"
    assert all(legacy_module not in vars(module) for module in modules)
