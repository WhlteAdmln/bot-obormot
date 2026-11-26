# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Basic history commands: clear, forget and show the current limit."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot_obormot.handlers.history import texts
from bot_obormot.handlers.prompt.handler import send_prompt_status
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings


async def cmd_history_clear(
    message: Message, state: FSMContext, database: Database
) -> None:
    """Clears the dialog history of the user."""
    if message.from_user is None:
        return

    await database.reset_history(message.from_user.id)

    await send_prompt_status(
        message,
        state,
        texts.HISTORY_CLEARED,
    )


async def cmd_forget_me(
    message: Message, state: FSMContext, database: Database
) -> None:
    """Delete all stored data belonging to the user."""
    if message.from_user is None:
        return

    await database.forget_user(message.from_user.id)

    await send_prompt_status(
        message,
        state,
        texts.USER_DATA_DELETED,
    )


async def show_history_limit(
    message: Message, state: FSMContext, settings: Settings, database: Database
) -> None:
    """Show the current history limit in a temporary message."""
    if message.from_user is None:
        return

    user_id = message.from_user.id
    current_limit = await database.get_history_limit(user_id)

    await send_prompt_status(
        message,
        state,
        texts.HISTORY_LIMIT_STATUS.format(
            current_limit=current_limit,
            default_limit=settings.DEFAULT_HISTORY_EXCHANGES,
        ),
    )


async def cmd_history(
    message: Message,
    state: FSMContext,
    settings: Settings,
    database: Database,
) -> None:
    """Shows the current history limit of the user."""
    await show_history_limit(message, state, settings, database)


def create_router() -> Router:
    """Build a router with the basic history commands."""
    router = Router()
    router.message.register(cmd_history_clear, Command("history_clear"))
    router.message.register(cmd_forget_me, Command("forget_me"))
    router.message.register(cmd_history, Command("history"))
    return router
