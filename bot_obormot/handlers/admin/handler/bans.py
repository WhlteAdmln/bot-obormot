# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Commands that ban and unban users."""

from aiogram.filters import CommandObject
from aiogram.types import Message

from bot_obormot.handlers.admin import texts
from bot_obormot.handlers.admin.handler.access import (
    audit_denied,
    is_admin_or_supervisor,
)
from bot_obormot.services.audit import audit
from bot_obormot.services.database import Database
from bot_obormot.settings import Settings


def _parse_target_id(command: CommandObject) -> int | None:
    try:
        target_id = int((command.args or "").strip())
    except ValueError:
        return None
    return target_id if target_id > 0 else None


async def cmd_ban(
    message: Message,
    command: CommandObject,
    settings: Settings,
    database: Database,
) -> None:
    """Ban a user until a separate /unban command is issued."""
    if message.from_user is None:
        return

    actor_id = message.from_user.id
    if not await is_admin_or_supervisor(actor_id, settings, database):
        audit_denied(message)
        await message.answer(texts.ACCESS_DENIED)
        return

    target_id = _parse_target_id(command)
    if target_id is None:
        await message.answer(texts.TARGET_ID_PROMPT.format(command="ban"))
        return

    if (
        target_id == settings.SUPERVISOR_ID
        or target_id in await database.get_admin_ids()
    ):
        await message.answer(texts.BAN_PROTECTED_TARGET)
        return

    changed = await database.block_user(target_id)
    audit("ban", actor_id, target_id, "blocked" if changed else "already")
    await message.answer(
        texts.USER_BANNED.format(target_id=target_id)
        if changed
        else texts.USER_ALREADY_BANNED.format(target_id=target_id)
    )


async def cmd_unban(
    message: Message,
    command: CommandObject,
    settings: Settings,
    database: Database,
) -> None:
    """Remove a user's ban."""
    if message.from_user is None:
        return

    actor_id = message.from_user.id
    if not await is_admin_or_supervisor(actor_id, settings, database):
        audit_denied(message)
        await message.answer(texts.ACCESS_DENIED)
        return

    target_id = _parse_target_id(command)
    if target_id is None:
        await message.answer(texts.TARGET_ID_PROMPT.format(command="unban"))
        return

    changed = await database.unblock_user(target_id)
    audit("unban", actor_id, target_id, "unblocked" if changed else "not_found")
    await message.answer(
        texts.USER_UNBANNED.format(target_id=target_id)
        if changed
        else texts.USER_NOT_BANNED.format(target_id=target_id)
    )
