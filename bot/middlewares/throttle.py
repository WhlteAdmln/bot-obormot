"""Ограничение частоты входящих событий от одного пользователя."""

import time
from collections import OrderedDict
from collections.abc import Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class ThrottleMiddleware(BaseMiddleware):
    """Отбрасывает сообщения, если пользователь шлёт их слишком часто."""

    def __init__(
        self,
        max_events: int = 10,
        window_seconds: float = 10.0,
        max_tracked_users: int = 5000,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if max_events <= 0:
            raise ValueError("max_events must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if max_tracked_users <= 0:
            raise ValueError("max_tracked_users must be positive")

        self.max_events = max_events
        self.window = window_seconds
        self.max_tracked_users = max_tracked_users
        self._clock = clock or time.monotonic
        # OrderedDict ограничивает память и вытесняет давно неактивных
        # пользователей при появлении новых идентификаторов.
        self._events: OrderedDict[int, list[float]] = OrderedDict()

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")

        if user is None:
            return None

        now = self._clock()
        recent = self._events.pop(user.id, [])
        recent = [timestamp for timestamp in recent if now - timestamp < self.window]

        if len(recent) >= self.max_events:
            self._remember(user.id, recent)
            return None

        recent.append(now)
        self._remember(user.id, recent)

        return await handler(event, data)

    def _remember(self, user_id: int, timestamps: list[float]) -> None:
        self._events[user_id] = timestamps

        while len(self._events) > self.max_tracked_users:
            self._events.popitem(last=False)
