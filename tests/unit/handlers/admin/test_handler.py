# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the admin handler router."""

from bot_obormot.handlers.admin import handler
from bot_obormot.handlers.admin.handler.bans import cmd_ban, cmd_unban


def test_registers_ban_commands_on_the_router() -> None:
    callbacks = {registered.callback for registered in handler.router.message.handlers}

    expected = {cmd_ban, cmd_unban}
    assert expected <= callbacks, "/ban and /unban are not registered on the router"
