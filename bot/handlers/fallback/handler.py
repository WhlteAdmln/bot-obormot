# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fallback handler for unknown slash commands."""

from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.fsm.keys import UNKNOWN_COMMAND_MESSAGE_KEY, UNKNOWN_COMMAND_STATUS_MESSAGE_KEY
from bot.handlers.fallback.texts import UNKNOWN_COMMAND_MESSAGE

router = Router()


@router.message(F.text.startswith("/"))
async def cmd_unknown(message: Message, state: FSMContext) -> None:
    """Handle unknown commands."""
    response = await message.answer(UNKNOWN_COMMAND_MESSAGE)

    data: dict[str, Any] = {
        UNKNOWN_COMMAND_MESSAGE_KEY: message.message_id,
        UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: response.message_id,
    }
    await state.update_data(**data)
