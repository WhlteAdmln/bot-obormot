import time

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import TelegramObject

from bot.config import config
from bot.services.access import user_has_access
from bot.services.database import db

# Как часто можно повторять один и тот же отказ одному человеку.
DENY_NOTICE_INTERVAL = 60.0
# Предел размера таблицы «кому уже отказали» (защита памяти от спама).
MAX_TRACKED_DENIED = 5000


class AccessMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._last_denied_notice: dict[int, float] = {}

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")

        # Нет отправителя: не обрабатываем событие.
        if user is None:
            return None

        # Бот работает только в личных чатах.
        # История и системный промпт привязаны к пользователю, а не к чату,
        # поэтому в группе они могли бы раскрыться посторонним.
        chat = data.get("event_chat")

        if chat is not None and chat.type != ChatType.PRIVATE:
            return None

        allowed = await user_has_access(
            user.id,
            supervisor_id=config.SUPERVISOR_ID,
            allowed_users=config.ALLOWED_USERS,
            allow_all=config.ALLOW_ALL_USERS,
            database=db,
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
            await event.answer("⛔ У тебя нет доступа к этому боту.")
