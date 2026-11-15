# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Вспомогательные действия Telegram во время обработки запроса."""

import asyncio
from typing import TYPE_CHECKING, cast

from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

if TYPE_CHECKING:
    from aiogram import Bot


async def keep_typing(message: Message) -> None:
    """Поддерживает статус «печатает...» во время обработки сообщения."""
    bot = cast("Bot", message.bot)
    async with ChatActionSender.typing(
        bot=bot,
        chat_id=message.chat.id,
    ):
        await asyncio.Event().wait()
