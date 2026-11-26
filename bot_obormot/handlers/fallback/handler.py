# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fallback handler for unknown slash commands."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot_obormot.fsm.keys import (
    UNKNOWN_COMMAND_MESSAGE_KEY,
    UNKNOWN_COMMAND_STATUS_MESSAGE_KEY,
)
from bot_obormot.handlers.fallback.texts import UNKNOWN_COMMAND_MESSAGE


async def cmd_unknown(message: Message, state: FSMContext) -> None:
    """Handle unknown commands."""
    response = await message.answer(UNKNOWN_COMMAND_MESSAGE)

    data: dict[str, int] = {
        UNKNOWN_COMMAND_MESSAGE_KEY: message.message_id,
        UNKNOWN_COMMAND_STATUS_MESSAGE_KEY: response.message_id,
    }
    await state.update_data(data)


def create_router() -> Router:
    """Build a router with the unknown command handler."""
    router = Router()
    router.message.register(cmd_unknown, F.text.startswith("/"))
    return router
