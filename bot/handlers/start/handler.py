# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Handler of the /start command."""

import logging
from typing import TYPE_CHECKING, Any, cast

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    Message,
)

from bot.fsm.keys import WELCOME_MESSAGE_KEY
from bot.handlers.start import texts
from bot.services.database import Database
from bot.settings import Settings

if TYPE_CHECKING:
    from aiogram import Bot

router = Router()
logger = logging.getLogger("bot.handlers.start")


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    state: FSMContext,
    settings: Settings,
    database: Database,
) -> None:
    """Registers the command menu for the user and sends the welcome message."""
    if message.from_user is None:
        return

    user_id = message.from_user.id

    # The supervisor always has access to administrative features.
    is_admin = user_id == settings.SUPERVISOR_ID

    # Check regular administrators against SQLite.
    if not is_admin:
        try:
            admin_ids = await database.get_admin_ids()
            is_admin = user_id in admin_ids

        except Exception:
            logger.exception("Could not load administrators for the /start menu")
            is_admin = False

    # Build a per-user Telegram command menu.
    commands = [
        BotCommand(command="start", description=texts.START_COMMAND_DESCRIPTION),
        BotCommand(command="history", description=texts.HISTORY_COMMAND_DESCRIPTION),
        BotCommand(
            command="history_limit",
            description=texts.HISTORY_LIMIT_COMMAND_DESCRIPTION,
        ),
        BotCommand(
            command="history_clear",
            description=texts.HISTORY_CLEAR_COMMAND_DESCRIPTION,
        ),
        BotCommand(
            command="forget_me",
            description=texts.FORGET_ME_COMMAND_DESCRIPTION,
        ),
        BotCommand(command="prompt", description=texts.PROMPT_COMMAND_DESCRIPTION),
        BotCommand(
            command="prompt_set",
            description=texts.PROMPT_SET_COMMAND_DESCRIPTION,
        ),
        BotCommand(
            command="prompt_reset",
            description=texts.PROMPT_RESET_COMMAND_DESCRIPTION,
        ),
        BotCommand(command="cancel", description=texts.CANCEL_COMMAND_DESCRIPTION),
    ]

    if is_admin:
        commands.extend(
            [
                BotCommand(
                    command="health",
                    description=texts.HEALTH_COMMAND_DESCRIPTION,
                ),
                BotCommand(
                    command="ban",
                    description=texts.BAN_COMMAND_DESCRIPTION,
                ),
                BotCommand(
                    command="unban",
                    description=texts.UNBAN_COMMAND_DESCRIPTION,
                ),
            ]
        )

    # Administrator management is available only to the supervisor.
    if user_id == settings.SUPERVISOR_ID:
        commands.extend(
            [
                BotCommand(
                    command="admin",
                    description=texts.ADMIN_COMMAND_DESCRIPTION,
                ),
                BotCommand(
                    command="admins",
                    description=texts.ADMINS_COMMAND_DESCRIPTION,
                ),
                BotCommand(
                    command="admin_add",
                    description=texts.ADMIN_ADD_COMMAND_DESCRIPTION,
                ),
                BotCommand(
                    command="admin_remove",
                    description=texts.ADMIN_REMOVE_COMMAND_DESCRIPTION,
                ),
            ]
        )

    bot = cast("Bot", message.bot)
    await bot.set_my_commands(
        commands=commands,
        scope=BotCommandScopeChat(chat_id=message.chat.id),
    )

    text = texts.WELCOME_MESSAGE

    if is_admin:
        text += texts.ADMIN_HELP_MESSAGE.format(
            max_history_exchanges=settings.MAX_HISTORY_EXCHANGES,
        )

    # Only the supervisor can see administrator management commands.
    if user_id == settings.SUPERVISOR_ID:
        text += texts.SUPERVISOR_HELP_MESSAGE

    text += texts.CAPABILITIES_MESSAGE

    response = await message.answer(text)

    data: dict[str, Any] = {WELCOME_MESSAGE_KEY: response.message_id}
    await state.update_data(**data)
