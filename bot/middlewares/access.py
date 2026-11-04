from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.config import config
from bot.services.access import user_has_access
from bot.services.database import db


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")

        if user is None:
            return await handler(event, data)

        allowed = await user_has_access(
            user.id,
            supervisor_id=config.SUPERVISOR_ID,
            allowed_users=config.ALLOWED_USERS,
            database=db,
        )

        if not allowed:
            if hasattr(event, "answer"):
                await event.answer("⛔ У тебя нет доступа к этому боту.")
            return None

        return await handler(event, data)
