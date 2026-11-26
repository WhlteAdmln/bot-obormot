# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""History limit commands for users and administrators."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.command import CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot_obormot.handlers.history import texts
from bot_obormot.handlers.prompt.handler import send_prompt_status
from bot_obormot.services.audit import audit
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings

# Number of arguments in "/history_limit ID LIMIT".
_ARGS_WITH_TARGET_USER = 2


async def is_history_admin(
    user_id: int,
    settings: Settings,
    database: Database,
) -> bool:
    """Check whether the user is the supervisor or an administrator."""
    if user_id == settings.SUPERVISOR_ID:
        return True

    return user_id in await database.get_admin_ids()


async def _set_own_limit(
    message: Message,
    state: FSMContext,
    raw_limit: str,
    *,
    is_admin: bool,
    settings: Settings,
    database: Database,
) -> None:
    """Sets the history limit of the sender."""
    if message.from_user is None:
        return

    user_id = message.from_user.id

    try:
        exchange_limit = int(raw_limit)
    except ValueError:
        await send_prompt_status(
            message,
            state,
            texts.OWN_LIMIT_INTEGER_REQUIRED,
        )
        return

    maximum = (
        settings.MAX_HISTORY_EXCHANGES
        if is_admin
        else settings.DEFAULT_HISTORY_EXCHANGES
    )

    if not 1 <= exchange_limit <= maximum:
        await send_prompt_status(
            message,
            state,
            texts.HISTORY_LIMIT_RANGE.format(maximum=maximum),
        )
        return

    await database.set_history_limit(user_id, exchange_limit)

    await send_prompt_status(
        message,
        state,
        texts.OWN_LIMIT_UPDATED.format(exchange_limit=exchange_limit),
    )


def _parse_target_limit(args: list[str], settings: Settings) -> tuple[int, int] | str:
    """Return (target user ID, limit) or the user-facing error text."""
    try:
        target_user_id, exchange_limit = int(args[0]), int(args[1])
    except ValueError:
        return texts.TARGET_LIMIT_ARGUMENTS_INVALID

    if target_user_id <= 0:
        return texts.TARGET_USER_ID_POSITIVE_REQUIRED

    if not 1 <= exchange_limit <= settings.MAX_HISTORY_EXCHANGES:
        return texts.HISTORY_LIMIT_RANGE.format(
            maximum=settings.MAX_HISTORY_EXCHANGES,
        )

    return target_user_id, exchange_limit


async def _set_user_limit(
    message: Message,
    state: FSMContext,
    args: list[str],
    *,
    is_admin: bool,
    settings: Settings,
    database: Database,
) -> None:
    """Sets the history limit of another user (administrators only)."""
    if message.from_user is None:
        return

    user_id = message.from_user.id

    if not is_admin:
        await send_prompt_status(message, state, texts.TARGET_LIMIT_ADMIN_REQUIRED)
        return

    parsed = _parse_target_limit(args, settings)
    if isinstance(parsed, str):
        await send_prompt_status(message, state, parsed)
        return

    target_user_id, exchange_limit = parsed
    await database.set_history_limit(target_user_id, exchange_limit)
    audit(
        "history_limit_set",
        user_id,
        target_user_id,
        str(exchange_limit),
    )

    await send_prompt_status(
        message,
        state,
        texts.TARGET_LIMIT_UPDATED % (target_user_id, exchange_limit),
    )


async def cmd_history_limit(
    message: Message,
    state: FSMContext,
    command: CommandObject,
    settings: Settings,
    database: Database,
) -> None:
    """Shows usage or sets the history limit of the sender or of another user."""
    if message.from_user is None:
        return

    user_id = message.from_user.id
    args = (command.args or "").split()

    is_admin = await is_history_admin(user_id, settings, database)

    if len(args) == 1:
        # One argument: set the sender's limit.
        await _set_own_limit(
            message,
            state,
            args[0],
            is_admin=is_admin,
            settings=settings,
            database=database,
        )
    elif len(args) == _ARGS_WITH_TARGET_USER:
        # Two arguments: set another user's limit.
        await _set_user_limit(
            message,
            state,
            args,
            is_admin=is_admin,
            settings=settings,
            database=database,
        )
    else:
        # No arguments show usage instructions; more than two is an error.
        text = (
            texts.HISTORY_LIMIT_USAGE
            if not args
            else texts.HISTORY_LIMIT_TOO_MANY_ARGUMENTS
        )
        await send_prompt_status(message, state, text)


def create_router() -> Router:
    """Build a router with the history limit command."""
    router = Router()
    router.message.register(cmd_history_limit, Command("history_limit"))
    return router
