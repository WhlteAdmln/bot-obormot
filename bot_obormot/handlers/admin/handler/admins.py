# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Supervisor commands that show and manage the administrators."""

from aiogram.filters import CommandObject
from aiogram.types import Message

from bot_obormot.handlers.admin import texts
from bot_obormot.handlers.admin.handler.access import audit_denied, is_supervisor
from bot_obormot.services.audit import audit
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings


async def cmd_admin(
    message: Message,
    settings: Settings,
    database: Database,
) -> None:
    """Shows the admin panel summary to the supervisor."""
    if not is_supervisor(message, settings):
        audit_denied(message)
        await message.answer(texts.ACCESS_DENIED)
        return

    admin_ids = await database.get_admin_ids()

    await message.answer(
        texts.ADMIN_PANEL_TITLE
        + f"👑 Supervisor ID: {settings.SUPERVISOR_ID}\n"
        + texts.ADMIN_PANEL_ADMIN_COUNT.format(count=len(admin_ids))
        + texts.ADMIN_PANEL_ALLOWLIST_COUNT.format(count=len(settings.ALLOWED_USERS))
        + texts.ADMIN_PANEL_COMMANDS_TITLE
        + texts.ADMIN_PANEL_ADMINS_COMMAND
        + texts.ADMIN_PANEL_ADMIN_ADD_COMMAND
        + texts.ADMIN_PANEL_ADMIN_REMOVE_COMMAND
    )


async def cmd_admins(
    message: Message,
    settings: Settings,
    database: Database,
) -> None:
    """Lists the supervisor and regular administrators."""
    if not is_supervisor(message, settings):
        audit_denied(message)
        await message.answer(texts.ACCESS_DENIED)
        return

    admin_ids = sorted(await database.get_admin_ids())

    text = texts.ADMIN_LIST_TITLE.format(supervisor_id=settings.SUPERVISOR_ID)

    if admin_ids:
        text += texts.ADMIN_LIST_REGULAR_TITLE
        text += "\n".join(f"• {user_id}" for user_id in admin_ids)
    else:
        text += texts.ADMIN_LIST_EMPTY

    await message.answer(text)


async def cmd_admin_add(
    message: Message,
    command: CommandObject,
    settings: Settings,
    database: Database,
) -> None:
    """Adds an administrator by Telegram ID (supervisor only)."""
    if not is_supervisor(message, settings) or message.from_user is None:
        audit_denied(message)
        await message.answer(texts.ACCESS_DENIED)
        return

    argument = (command.args or "").strip()

    if not argument:
        await message.answer(texts.ADMIN_ID_PROMPT.format(command="admin_add"))
        return

    try:
        user_id = int(argument)
    except ValueError:
        await message.answer(texts.TELEGRAM_ID_INTEGER_REQUIRED)
        return

    if user_id <= 0:
        await message.answer(texts.TELEGRAM_ID_POSITIVE_REQUIRED)
        return

    if user_id == settings.SUPERVISOR_ID:
        await message.answer(texts.ALREADY_SUPERVISOR)
        return

    added = await database.add_admin(user_id)
    audit(
        "admin_add",
        message.from_user.id,
        user_id,
        "added" if added else "already",
    )

    if added:
        await message.answer(texts.ADMIN_ADDED.format(user_id=user_id))
    else:
        await message.answer(texts.ADMIN_ALREADY_EXISTS.format(user_id=user_id))


async def cmd_admin_remove(
    message: Message,
    command: CommandObject,
    settings: Settings,
    database: Database,
) -> None:
    """Removes an administrator by Telegram ID (supervisor only)."""
    if not is_supervisor(message, settings) or message.from_user is None:
        audit_denied(message)
        await message.answer(texts.ACCESS_DENIED)
        return

    argument = (command.args or "").strip()

    if not argument:
        await message.answer(texts.ADMIN_ID_PROMPT.format(command="admin_remove"))
        return

    try:
        user_id = int(argument)
    except ValueError:
        await message.answer(texts.TELEGRAM_ID_INTEGER_REQUIRED)
        return

    if user_id <= 0:
        await message.answer(texts.TELEGRAM_ID_POSITIVE_REQUIRED)
        return

    if user_id == settings.SUPERVISOR_ID:
        await message.answer(texts.SUPERVISOR_CANNOT_BE_REMOVED)
        return

    removed = await database.remove_admin(user_id)
    audit(
        "admin_remove",
        message.from_user.id,
        user_id,
        "removed" if removed else "not_found",
    )

    if removed:
        await message.answer(texts.ADMIN_REMOVED.format(user_id=user_id))
    else:
        await message.answer(texts.ADMIN_NOT_FOUND.format(user_id=user_id))
