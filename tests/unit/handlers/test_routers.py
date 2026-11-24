# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for handlers routers."""

from bot_obormot.handlers import admin, fallback, prompt, routers, start
from bot_obormot.handlers.chat import handler as chat_handler
from bot_obormot.handlers.history import basic as history_basic
from bot_obormot.handlers.history import limits as history_limits


def test_handler_package_routers_are_exported() -> None:
    assert start.router is not None
    assert admin.router is not None
    assert history_basic.router is not None
    assert history_limits.router is not None
    assert prompt.router is not None
    assert fallback.router is not None
    assert routers.router is not None
    assert chat_handler.router is not None


def test_routers_module_keeps_original_registration_groups_in_order() -> None:
    assert routers.router.sub_routers == [
        history_basic.router,
        prompt.router,
        history_limits.router,
        fallback.router,
    ]


def test_unknown_command_router_is_last() -> None:
    assert routers.router.sub_routers[-1] is fallback.router
    assert len(fallback.router.message.handlers) == 1


def test_routers_module_only_exports_router() -> None:
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
