# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Recording next handler for aiogram middleware tests."""

from aiogram.types import TelegramObject

from bot_obormot.middlewares.aliases import MiddlewareData


class RecordingHandler:
    """Record the events a middleware passes on and return a fixed result."""

    def __init__(
        self,
        result: object = "handled",
        error: Exception | None = None,
    ) -> None:
        """Create a handler that returns ``result`` or raises ``error``."""
        self.result = result
        self.error = error
        self.events: list[TelegramObject] = []

    async def __call__(self, event: TelegramObject, data: MiddlewareData) -> object:
        """Record the event and return the configured result."""
        _ = data
        self.events.append(event)
        if self.error is not None:
            raise self.error
        return self.result
