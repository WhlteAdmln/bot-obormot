# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

from bot.fsm.keys import PROMPT_FLOW_KEY, WELCOME_MESSAGE_KEY
from bot.fsm.states import PromptStates
from bot.handlers import admin, chat, commands, fallback, history, prompt, start
from bot.handlers.admin.handler import cmd_ban, cmd_unban
from bot.handlers.history.basic import cmd_forget_me
from bot.middlewares.temporary_messages import TemporaryMessagesCleanupMiddleware


def test_handler_package_routers_are_exported():
    assert start.router is not None
    assert admin.router is not None
    assert history.basic.router is not None
    assert history.limits.router is not None
    assert prompt.router is not None
    assert fallback.router is not None
    assert commands.router is not None
    assert chat.router is not None


def test_fsm_and_middleware_imports_use_canonical_modules():
    assert PromptStates.waiting_for_prompt is not None
    assert PROMPT_FLOW_KEY == "prompt_flow_message_ids"
    assert WELCOME_MESSAGE_KEY == "start_welcome_message_id"
    assert (
        TemporaryMessagesCleanupMiddleware.__module__
        == "bot.middlewares.temporary_messages.middleware"
    )


def test_commands_router_keeps_original_registration_groups_in_order():
    assert commands.router.sub_routers == [
        history.basic.router,
        prompt.router,
        history.limits.router,
        fallback.router,
    ]


def test_unknown_command_router_is_last():
    assert commands.router.sub_routers[-1] is fallback.router
    assert len(fallback.router.message.handlers) == 1


def test_forget_me_command_is_registered():
    assert any(
        handler.callback is cmd_forget_me
        for handler in history.basic.router.message.handlers
    )


def test_ban_commands_are_registered():
    callbacks = {handler.callback for handler in admin.router.message.handlers}
    assert cmd_ban in callbacks
    assert cmd_unban in callbacks


def test_commands_package_only_exports_router():
    assert commands.__all__ == ["router"]
    assert set(vars(commands).keys()).isdisjoint(
        {
            "cmd_history_clear",
            "cmd_history",
            "cmd_prompt",
            "cmd_prompt_set",
            "cmd_history_limit",
            "cmd_unknown",
        }
    )
