# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for handlers routers."""

from collections.abc import Callable

import pytest
from aiogram import Router

from bot_obormot.handlers import admin, fallback, prompt, routers, start
from bot_obormot.handlers.chat import handler as chat_handler
from bot_obormot.handlers.fallback import cmd_unknown
from bot_obormot.handlers.history import basic as history_basic
from bot_obormot.handlers.history import limits as history_limits
from bot_obormot.handlers.history.basic import cmd_history_clear
from bot_obormot.handlers.history.limits import cmd_history_limit
from bot_obormot.handlers.prompt import cmd_prompt
from bot_obormot.services.chat.aggregation import MessageAggregator
from bot_obormot.services.chat.locks import UserLocks
from bot_obormot.services.media import MediaSlots
from bot_obormot.services.telegram import TelegramDownloader


def _create_chat_router() -> Router:
    """Build the chat router with a fresh runtime of one bot."""
    runtime = chat_handler.ChatRuntime(
        message_aggregator=MessageAggregator(),
        user_locks=UserLocks(),
        downloader=TelegramDownloader(),
        media_slots=MediaSlots(),
    )
    return chat_handler.create_router(runtime)


ROUTER_FACTORIES = [
    start.create_router,
    admin.create_router,
    history_basic.create_router,
    history_limits.create_router,
    prompt.create_router,
    fallback.create_router,
    routers.create_router,
    _create_chat_router,
]


@pytest.mark.parametrize("create_router", ROUTER_FACTORIES)
def test_builds_a_router_in_each_handler_module(
    create_router: Callable[[], Router],
) -> None:
    assert isinstance(create_router(), Router), "a factory does not build a router"


@pytest.mark.parametrize("create_router", ROUTER_FACTORIES)
def test_builds_a_new_router_on_each_call(
    create_router: Callable[[], Router],
) -> None:
    first = create_router()
    assert create_router() is not first, "a factory returns a shared router"


def test_keeps_original_registration_groups_in_order() -> None:
    expected_callbacks = [
        cmd_history_clear,
        cmd_prompt,
        cmd_history_limit,
        cmd_unknown,
    ]
    first_callbacks = [
        sub_router.message.handlers[0].callback
        for sub_router in routers.create_router().sub_routers
    ]
    assert first_callbacks == expected_callbacks, "sub-router order changed"


def test_registers_unknown_command_router_last() -> None:
    expected_callbacks = [cmd_unknown]
    last_router = routers.create_router().sub_routers[-1]
    callbacks = [handler.callback for handler in last_router.message.handlers]
    assert callbacks == expected_callbacks, "the fallback router is not the last one"


def test_registers_a_single_unknown_command_handler() -> None:
    expected_count = 1
    handler_count = len(fallback.create_router().message.handlers)
    assert handler_count == expected_count, "the fallback router has extra handlers"


def test_exports_only_router_factory_from_routers_module() -> None:
    expected_exports = ["create_router"]
    assert routers.__all__ == expected_exports, "routers exports more than the factory"


def test_keeps_handler_functions_out_of_routers_module() -> None:
    handler_names = {
        "cmd_history_clear",
        "cmd_history",
        "cmd_prompt",
        "cmd_prompt_set",
        "cmd_history_limit",
        "cmd_unknown",
    }
    module_names = set(vars(routers).keys())
    assert module_names.isdisjoint(handler_names), "routers re-exports handlers"
