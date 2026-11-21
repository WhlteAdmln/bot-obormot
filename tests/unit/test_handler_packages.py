# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for handler packages."""

from bot_obormot.fsm.keys import PROMPT_FLOW_KEY, WELCOME_MESSAGE_KEY
from bot_obormot.fsm.states import PromptStates
from bot_obormot.handlers import admin, fallback, prompt, routers, start
from bot_obormot.handlers.admin import handler as admin_handler
from bot_obormot.handlers.admin.handler import cmd_ban, cmd_unban
from bot_obormot.handlers.chat import handler as chat_handler
from bot_obormot.handlers.history import basic as history_basic
from bot_obormot.handlers.history import limits as history_limits
from bot_obormot.handlers.history.basic import cmd_forget_me
from bot_obormot.handlers.start import handler as start_handler
from bot_obormot.middlewares import access as access_middleware
from bot_obormot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)


def test_handler_package_routers_are_exported() -> None:
    """Handler package routers are exported."""
    assert start.router is not None
    assert admin.router is not None
    assert history_basic.router is not None
    assert history_limits.router is not None
    assert prompt.router is not None
    assert fallback.router is not None
    assert routers.router is not None
    assert chat_handler.router is not None


def test_fsm_and_middleware_imports_use_canonical_modules() -> None:
    """Fsm and middleware imports use canonical modules."""
    assert PromptStates.waiting_for_prompt is not None
    assert PROMPT_FLOW_KEY == "prompt_flow_message_ids"
    assert WELCOME_MESSAGE_KEY == "start_welcome_message_id"
    assert (
        TemporaryMessagesCleanupMiddleware.__module__
        == "bot_obormot.middlewares.temporary_messages.middleware"
    )


def test_routers_module_keeps_original_registration_groups_in_order() -> None:
    """Routers module keeps original registration groups in order."""
    assert routers.router.sub_routers == [
        history_basic.router,
        prompt.router,
        history_limits.router,
        fallback.router,
    ]


def test_unknown_command_router_is_last() -> None:
    """Unknown command router is last."""
    assert routers.router.sub_routers[-1] is fallback.router
    assert len(fallback.router.message.handlers) == 1


def test_forget_me_command_is_registered() -> None:
    """Forget me command is registered."""
    assert any(
        handler.callback is cmd_forget_me
        for handler in history_basic.router.message.handlers
    )


def test_ban_commands_are_registered() -> None:
    """Ban commands are registered."""
    callbacks = {handler.callback for handler in admin.router.message.handlers}
    assert cmd_ban in callbacks
    assert cmd_unban in callbacks


def test_routers_module_only_exports_router() -> None:
    """Routers module only exports router."""
    assert routers.__all__ == ["router"]
    assert set(vars(routers).keys()).isdisjoint(
        {
            "cmd_history_clear",
            "cmd_history",
            "cmd_prompt",
            "cmd_prompt_set",
            "cmd_history_limit",
            "cmd_unknown",
        }
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
