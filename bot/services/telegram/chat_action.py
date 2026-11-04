"""Вспомогательные действия Telegram во время обработки запроса."""

import asyncio

from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender


async def keep_typing(message: Message) -> None:
    """Поддерживает статус «печатает...» во время обработки сообщения."""

    async with ChatActionSender.typing(
        bot=message.bot,
        chat_id=message.chat.id,
    ):
        await asyncio.Event().wait()
