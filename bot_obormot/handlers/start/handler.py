# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Handler of the /start command."""

import logging
from typing import TYPE_CHECKING, cast

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    Message,
)

from bot_obormot.fsm.keys import WELCOME_MESSAGE_KEY
from bot_obormot.handlers.start import texts
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger("bot_obormot.handlers.start")


async def _is_admin(user_id: int, settings: Settings, database: Database) -> bool:
    """Return whether the user may see administrative features."""
    # The supervisor always has access to administrative features.
    if user_id == settings.SUPERVISOR_ID:
        return True

    # Check regular administrators against SQLite.
    try:
        admin_ids = await database.get_admin_ids()
    except Exception:
        logger.exception("Could not load administrators for the /start menu")
        return False
    return user_id in admin_ids


def _command(command: str, description: str) -> BotCommand:
    """Build one Telegram command menu entry."""
    return BotCommand(command=command, description=description)


def _build_commands(*, is_admin: bool, is_supervisor: bool) -> list[BotCommand]:
    """Build the per-user Telegram command menu."""
    commands = [
        _command("start", texts.START_COMMAND_DESCRIPTION),
        _command("history", texts.HISTORY_COMMAND_DESCRIPTION),
        _command("history_limit", texts.HISTORY_LIMIT_COMMAND_DESCRIPTION),
        _command("history_clear", texts.HISTORY_CLEAR_COMMAND_DESCRIPTION),
        _command("forget_me", texts.FORGET_ME_COMMAND_DESCRIPTION),
        _command("prompt", texts.PROMPT_COMMAND_DESCRIPTION),
        _command("prompt_set", texts.PROMPT_SET_COMMAND_DESCRIPTION),
        _command("prompt_reset", texts.PROMPT_RESET_COMMAND_DESCRIPTION),
        _command("cancel", texts.CANCEL_COMMAND_DESCRIPTION),
    ]

    if is_admin:
        commands.extend(
            [
                _command("health", texts.HEALTH_COMMAND_DESCRIPTION),
                _command("ban", texts.BAN_COMMAND_DESCRIPTION),
                _command("unban", texts.UNBAN_COMMAND_DESCRIPTION),
            ]
        )

    # Administrator management is available only to the supervisor.
    if is_supervisor:
        commands.extend(
            [
                _command("admin", texts.ADMIN_COMMAND_DESCRIPTION),
                _command("admins", texts.ADMINS_COMMAND_DESCRIPTION),
                _command("admin_add", texts.ADMIN_ADD_COMMAND_DESCRIPTION),
                _command("admin_remove", texts.ADMIN_REMOVE_COMMAND_DESCRIPTION),
            ]
        )
    return commands


def _build_welcome_text(
    settings: Settings, *, is_admin: bool, is_supervisor: bool
) -> str:
    """Compose the welcome message for the user's role."""
    text = texts.WELCOME_MESSAGE

    if is_admin:
        text += texts.ADMIN_HELP_MESSAGE.format(
            max_history_exchanges=settings.MAX_HISTORY_EXCHANGES,
        )

    # Only the supervisor can see administrator management commands.
    if is_supervisor:
        text += texts.SUPERVISOR_HELP_MESSAGE

    return text + texts.CAPABILITIES_MESSAGE


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
    is_supervisor = user_id == settings.SUPERVISOR_ID
    is_admin = await _is_admin(user_id, settings, database)

    bot = cast("Bot", message.bot)
    await bot.set_my_commands(
        commands=_build_commands(is_admin=is_admin, is_supervisor=is_supervisor),
        scope=BotCommandScopeChat(chat_id=message.chat.id),
    )

    text = _build_welcome_text(settings, is_admin=is_admin, is_supervisor=is_supervisor)
    response = await message.answer(text)

    data: dict[str, int] = {WELCOME_MESSAGE_KEY: response.message_id}
    await state.update_data(data)


def create_router() -> Router:
    """Build a router with the /start command."""
    router = Router()
    router.message.register(cmd_start, Command("start"))
    return router
