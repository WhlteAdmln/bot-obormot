# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Vulture whitelist for aiogram handlers registered through decorators."""

# pylint: disable=invalid-name  # entries repeat the names vulture reports

handle_message: object = None
cmd_unknown: object = None

cmd_health: object = None
cmd_admin: object = None
cmd_admins: object = None
cmd_admin_add: object = None
cmd_admin_remove: object = None
cmd_ban: object = None
cmd_unban: object = None

cmd_start: object = None

cmd_prompt: object = None
cmd_prompt_set: object = None
save_prompt: object = None
cmd_prompt_reset: object = None
cmd_cancel: object = None

cmd_history_limit: object = None
cmd_history_clear: object = None
cmd_forget_me: object = None
cmd_history: object = None

_WHITELISTED_HANDLERS = (
    handle_message,
    cmd_unknown,
    cmd_health,
    cmd_admin,
    cmd_admins,
    cmd_admin_add,
    cmd_admin_remove,
    cmd_ban,
    cmd_unban,
    cmd_start,
    cmd_prompt,
    cmd_prompt_set,
    save_prompt,
    cmd_prompt_reset,
    cmd_cancel,
    cmd_history_limit,
    cmd_history_clear,
    cmd_forget_me,
    cmd_history,
)
