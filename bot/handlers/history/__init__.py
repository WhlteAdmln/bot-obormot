# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""History-related Telegram command modules.

The compatibility command router composes ``basic`` and ``limits`` separately
so the historical handler registration order remains unchanged.
"""

from bot.handlers.history import basic, limits

__all__ = ["basic", "limits"]
