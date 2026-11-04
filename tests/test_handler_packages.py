from bot.handlers import admin, chat, commands, fallback, history, prompt, start
from bot.handlers.commands import (
    PromptStates,
    PROMPT_FLOW_KEY,
    TemporaryMessagesCleanupMiddleware,
    cmd_unknown,
)
from bot.fsm.keys import WELCOME_MESSAGE_KEY
from bot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware as Middleware,
)


def test_handler_package_routers_are_exported():
    assert start.router is not None
    assert admin.router is not None
    assert history.basic.router is not None
    assert history.limits.router is not None
    assert prompt.router is not None
    assert fallback.router is not None
    assert commands.router is not None
    assert chat.router is not None


def test_command_compatibility_exports_are_preserved():
    assert PromptStates.waiting_for_prompt is not None
    assert PROMPT_FLOW_KEY == "prompt_flow_message_ids"
    assert WELCOME_MESSAGE_KEY == "start_welcome_message_id"
    assert cmd_unknown is fallback.cmd_unknown
    assert TemporaryMessagesCleanupMiddleware is Middleware


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
