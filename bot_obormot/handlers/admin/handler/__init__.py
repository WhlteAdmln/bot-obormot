# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Administrator commands: health checks, admin management, and user bans."""

from aiogram import Router
from aiogram.filters import Command

from bot_obormot.handlers.admin.handler.admins import (
    cmd_admin,
    cmd_admin_add,
    cmd_admin_remove,
    cmd_admins,
)
from bot_obormot.handlers.admin.handler.bans import cmd_ban, cmd_unban
from bot_obormot.handlers.admin.handler.health import cmd_health


def create_router() -> Router:
    """Build a router with the administrator commands."""
    router = Router()
    router.message.register(cmd_health, Command("health"))
    router.message.register(cmd_admin, Command("admin"))
    router.message.register(cmd_admins, Command("admins"))
    router.message.register(cmd_admin_add, Command("admin_add"))
    router.message.register(cmd_admin_remove, Command("admin_remove"))
    router.message.register(cmd_ban, Command("ban"))
    router.message.register(cmd_unban, Command("unban"))
    return router


__all__ = ["create_router"]
