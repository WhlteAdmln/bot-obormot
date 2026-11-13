# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Basic history commands: clear, forget and show the current limit."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.config import config
from bot.handlers.prompt.handler import send_prompt_status
from bot.services.database import db

router = Router()


@router.message(Command("history_clear"))
async def cmd_history_clear(message: Message, state: FSMContext) -> None:
    """Clears the dialog history of the user."""
    await db.reset_history(message.from_user.id)

    await send_prompt_status(
        message,
        state,
        "🧹 История диалога очищена.",
    )


@router.message(Command("forget_me"))
async def cmd_forget_me(message: Message, state: FSMContext) -> None:
    """Полностью удаляет сохранённые данные пользователя."""
    await db.forget_user(message.from_user.id)

    await send_prompt_status(
        message,
        state,
        "🧹 Все твои данные удалены.",
    )


async def show_history_limit(message: Message, state: FSMContext) -> None:
    """Показывает текущий лимит истории временным сообщением."""
    user_id = message.from_user.id
    current_limit = await db.get_history_limit(user_id)

    await send_prompt_status(
        message,
        state,
        f"📚 Твой лимит истории: {current_limit} полных обменов.\n"
        f"Стандартный лимит: {config.DEFAULT_HISTORY_EXCHANGES}.",
    )


@router.message(Command("history"))
async def cmd_history(message: Message, state: FSMContext) -> None:
    """Shows the current history limit of the user."""
    await show_history_limit(message, state)
