# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fallback handler for unknown slash commands."""

from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.fsm.keys import UNKNOWN_COMMAND_MESSAGE_KEY, UNKNOWN_COMMAND_STATUS_MESSAGE_KEY

router = Router()


@router.message(F.text.startswith("/"))
async def cmd_unknown(message: Message, state: FSMContext) -> None:
    """Обрабатывает неизвестные команды."""
    response = await message.answer("⛔ Доступ запрещён.")

    data: dict[str, Any] = {
        UNKNOWN_COMMAND_MESSAGE_KEY: message.message_id,
        UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: response.message_id,
    }
    await state.update_data(**data)
