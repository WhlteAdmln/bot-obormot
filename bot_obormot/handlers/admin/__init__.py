# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Admin handlers."""

from bot_obormot.handlers.admin.handler import create_router
from bot_obormot.handlers.admin.handler.access import is_supervisor
from bot_obormot.handlers.admin.handler.admins import (
    cmd_admin,
    cmd_admin_add,
    cmd_admin_remove,
    cmd_admins,
)
from bot_obormot.handlers.admin.handler.bans import cmd_ban, cmd_unban
from bot_obormot.handlers.admin.handler.health import (
    check_database,
    check_telegram,
    cmd_health,
)

__all__ = [
    "check_database",
    "check_telegram",
    "cmd_admin",
    "cmd_admin_add",
    "cmd_admin_remove",
    "cmd_admins",
    "cmd_ban",
    "cmd_health",
    "cmd_unban",
    "create_router",
    "is_supervisor",
]
