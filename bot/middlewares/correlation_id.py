# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Middleware that binds a Telegram update ID to the logging context."""

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.log_context import correlation_id
from bot.middlewares.aliases import MiddlewareData, NextHandler


class CorrelationIdMiddleware(BaseMiddleware):
    """Sets the correlation ID for the duration of one Telegram update."""

    async def __call__(
        self,
        handler: NextHandler,
        event: TelegramObject,
        data: MiddlewareData,
    ) -> object:
        """Run the update handler with its update ID in the logging context."""
        update_id = getattr(event, "update_id", None)
        token = correlation_id.set(str(update_id) if update_id is not None else "-")
        try:
            return await handler(event, data)
        finally:
            correlation_id.reset(token)
