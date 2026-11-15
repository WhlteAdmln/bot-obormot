# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Middleware for cleaning up temporary Telegram messages."""

from bot.middlewares.temporary_messages.middleware import (
    TemporaryMessagesCleanupMiddleware,
)

__all__ = ["TemporaryMessagesCleanupMiddleware"]
