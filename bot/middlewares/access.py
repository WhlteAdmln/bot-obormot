# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Middleware that restricts the bot to users who have access."""

import time
from typing import TYPE_CHECKING

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import TelegramObject

from bot.middlewares.aliases import MiddlewareData, NextHandler
from bot.middlewares.texts import ACCESS_DENIED_MESSAGE
from bot.services.access import user_has_access

if TYPE_CHECKING:
    from bot.services.database import Database
    from bot.settings import Settings

# Minimum interval between denial notices sent to the same user.
DENY_NOTICE_INTERVAL = 60.0
# Maximum size of the denied-user table to prevent excessive memory use.
MAX_TRACKED_DENIED = 5000


class AccessMiddleware(BaseMiddleware):
    """Drops events from users without access and notifies them occasionally."""

    def __init__(self) -> None:
        """Creates an empty table of recently notified users."""
        self._last_denied_notice: dict[int, float] = {}

    async def __call__(
        self,
        handler: NextHandler,
        event: TelegramObject,
        data: MiddlewareData,
    ) -> object:
        """Passes the event on only when the sender is allowed to use the bot."""
        user = data.get("event_from_user")

        # Do not process events without a sender.
        if user is None:
            return None

        # The bot operates only in private chats.
        # History and the system prompt belong to the user, not the chat,
        # so processing group messages could expose them to other people.
        chat = data.get("event_chat")

        if chat is not None and chat.type != ChatType.PRIVATE:
            return None

        settings: Settings = data["settings"]
        database: Database = data["database"]
        allowed = await user_has_access(
            user.id,
            supervisor_id=settings.SUPERVISOR_ID,
            allowed_users=settings.ALLOWED_USERS,
            allow_all=settings.ALLOW_ALL_USERS,
            database=database,
        )

        if allowed:
            return await handler(event, data)

        await self._notify_denied(event, user.id)
        return None

    async def _notify_denied(self, event: TelegramObject, user_id: int) -> None:
        now = time.monotonic()
        last = self._last_denied_notice.get(user_id)

        if last is not None and now - last < DENY_NOTICE_INTERVAL:
            return

        if len(self._last_denied_notice) >= MAX_TRACKED_DENIED:
            self._last_denied_notice.clear()

        self._last_denied_notice[user_id] = now

        if hasattr(event, "answer"):
            await event.answer(ACCESS_DENIED_MESSAGE)
