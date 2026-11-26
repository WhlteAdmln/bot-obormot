# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for handlers routers."""

import pytest
from aiogram import Router

from bot_obormot.handlers import admin, fallback, prompt, routers, start
from bot_obormot.handlers.chat import handler as chat_handler
from bot_obormot.handlers.history import basic as history_basic
from bot_obormot.handlers.history import limits as history_limits


@pytest.mark.parametrize(
    "exported",
    [
        start.router,
        admin.router,
        history_basic.router,
        history_limits.router,
        prompt.router,
        fallback.router,
        routers.router,
        chat_handler.router,
    ],
)
def test_exports_a_router_from_each_handler_module(exported: object) -> None:
    assert isinstance(exported, Router), "a handler module does not export a router"


def test_keeps_original_registration_groups_in_order() -> None:
    expected_routers = [
        history_basic.router,
        prompt.router,
        history_limits.router,
        fallback.router,
    ]
    assert routers.router.sub_routers == expected_routers, "sub-router order changed"


def test_registers_unknown_command_router_last() -> None:
    last_router = routers.router.sub_routers[-1]
    assert last_router is fallback.router, "the fallback router is not the last one"


def test_registers_a_single_unknown_command_handler() -> None:
    expected_count = 1
    handler_count = len(fallback.router.message.handlers)
    assert handler_count == expected_count, "the fallback router has extra handlers"


def test_exports_only_router_from_routers_module() -> None:
    expected_exports = ["router"]
    assert routers.__all__ == expected_exports, "routers exports more than the router"


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
