"""Middleware for cleaning up temporary Telegram messages."""

from bot.middlewares.temporary_messages.middleware import (
    TemporaryMessagesCleanupMiddleware,
)

__all__ = ["TemporaryMessagesCleanupMiddleware"]
