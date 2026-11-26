# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the admin handler router."""

from collections.abc import Callable

import pytest
from aiogram.filters import Command

from bot_obormot.handlers.admin import handler
from bot_obormot.handlers.admin.handler.admins import (
    cmd_admin,
    cmd_admin_add,
    cmd_admin_remove,
    cmd_admins,
)
from bot_obormot.handlers.admin.handler.bans import cmd_ban, cmd_unban
from bot_obormot.handlers.admin.handler.health import cmd_health


def _commands_of(callback: Callable[..., object]) -> list[tuple[str, ...]]:
    return [
        tuple(str(command) for command in registered_filter.callback.commands)
        for registered in handler.create_router().message.handlers
        if registered.callback is callback
        for registered_filter in registered.filters or []
        if isinstance(registered_filter.callback, Command)
    ]


@pytest.mark.parametrize(
    ("callback", "command"),
    [
        (cmd_health, "health"),
        (cmd_admin, "admin"),
        (cmd_admins, "admins"),
        (cmd_admin_add, "admin_add"),
        (cmd_admin_remove, "admin_remove"),
        (cmd_ban, "ban"),
        (cmd_unban, "unban"),
    ],
)
def test_registers_each_admin_handler_for_its_command_only(
    callback: Callable[..., object], command: str
) -> None:
    expected = [(command,)]
    assert _commands_of(callback) == expected, "an admin handler has the wrong command"


def test_registers_no_admin_handler_without_a_command_filter() -> None:
    unfiltered = [
        registered.callback.__name__
        for registered in handler.create_router().message.handlers
        if not any(
            isinstance(registered_filter.callback, Command)
            for registered_filter in registered.filters or []
        )
    ]
    expected_empty: list[str] = []
    assert unfiltered == expected_empty, "an admin handler accepts any message"
