# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fallback handlers, including unknown commands."""

from bot_obormot.handlers.fallback.handler import cmd_unknown, router

__all__ = [
    "cmd_unknown",
    "router",
]
