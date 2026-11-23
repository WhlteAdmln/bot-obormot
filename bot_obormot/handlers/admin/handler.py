# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Administrator commands: health checks, admin management, and user bans."""

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot_obormot.handlers.admin import texts
from bot_obormot.services.audit import audit
from bot_obormot.services.database import Database
from bot_obormot.services.llm.client import LLMClient
from bot_obormot.settings import Settings

if TYPE_CHECKING:
    from aiogram import Bot

router = Router()
logger = logging.getLogger("bot_obormot.handlers.admin")


def is_supervisor(message: Message, settings: Settings) -> bool:
    """Returns True when the message was sent by the configured supervisor."""
    if message.from_user is None:
        return False
    return message.from_user.id == settings.SUPERVISOR_ID


def _audit_denied(message: Message) -> None:
    """Record a denied admin command when the sender is known."""
    if message.from_user is not None:
        audit("admin_denied", message.from_user.id, None, "denied")


async def check_telegram(message: Message) -> tuple[bool, str]:
    """Check Telegram Bot API availability."""
    bot = cast("Bot", message.bot)
    try:
        await bot.get_me()

    except Exception:
        logger.exception("Telegram health check failed")
        return False, texts.TELEGRAM_UNAVAILABLE

    return True, texts.TELEGRAM_AVAILABLE


async def check_database(database: Database) -> tuple[bool, str]:
    """Check SQLite availability."""
    try:
        await database.health_check()

    except Exception:
        logger.exception("Database health check failed")
        return False, texts.DATABASE_CONNECTION_ERROR

    return True, texts.DATABASE_CONNECTED


@router.message(Command("health"))
async def cmd_health(
    message: Message,
    settings: Settings,
    llm_client: LLMClient,
    database: Database,
) -> None:
    """Show the status of the bot's main components."""
    if not message.from_user:
        return

    user_id = message.from_user.id

    # The supervisor always has access.
    # Other administrators are checked against SQLite.
    if not is_supervisor(message, settings):
        try:
            admin_ids = await database.get_admin_ids()

        except Exception:
            logger.exception("Could not verify admin permissions for /health")
            await message.answer(texts.ADMIN_PERMISSION_CHECK_FAILED)
            return

        if user_id not in admin_ids:
            audit("admin_denied", user_id, None, "denied")
            await message.answer(texts.ACCESS_DENIED)
            return

    status_message = await message.answer(texts.HEALTH_CHECK_IN_PROGRESS)

    # Run checks in parallel.
    telegram_result, database_result, llm_result = await asyncio.gather(
        check_telegram(message),
        check_database(database),
        llm_client.health_check(),
    )

    def format_status(
        name: str,
        result: tuple[bool, str],
    ) -> str:
        is_ok, detail = result
        icon = "🟢" if is_ok else "🔴"

        return f"{icon} {name}: {detail}"

    report = (
        texts.HEALTH_REPORT_TITLE
        + f"{format_status('Telegram API', telegram_result)}\n"
        + f"{format_status(texts.DATABASE_STATUS_LABEL, database_result)}\n"
        + f"{format_status(texts.INFERENCE_STATUS_LABEL, llm_result)}"
    )

    await status_message.edit_text(
        report,
        parse_mode="HTML",
    )


@router.message(Command("admin"))
async def cmd_admin(
    message: Message,
    settings: Settings,
    database: Database,
) -> None:
    """Shows the admin panel summary to the supervisor."""
    if not is_supervisor(message, settings):
        _audit_denied(message)
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


@router.message(Command("admins"))
async def cmd_admins(
    message: Message,
    settings: Settings,
    database: Database,
) -> None:
    """Lists the supervisor and regular administrators."""
    if not is_supervisor(message, settings):
        _audit_denied(message)
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


@router.message(Command("admin_add"))
async def cmd_admin_add(
    message: Message,
    command: CommandObject,
    settings: Settings,
    database: Database,
) -> None:
    """Adds an administrator by Telegram ID (supervisor only)."""
    if not is_supervisor(message, settings) or message.from_user is None:
        _audit_denied(message)
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


@router.message(Command("admin_remove"))
async def cmd_admin_remove(
    message: Message,
    command: CommandObject,
    settings: Settings,
    database: Database,
) -> None:
    """Removes an administrator by Telegram ID (supervisor only)."""
    if not is_supervisor(message, settings) or message.from_user is None:
        _audit_denied(message)
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


async def is_admin_or_supervisor(
    user_id: int,
    settings: Settings,
    database: Database,
) -> bool:
    """Check whether the user can manage user bans."""
    if user_id == settings.SUPERVISOR_ID:
        return True
    return user_id in await database.get_admin_ids()


def _parse_target_id(command: CommandObject) -> int | None:
    try:
        target_id = int((command.args or "").strip())
    except ValueError:
        return None
    return target_id if target_id > 0 else None


@router.message(Command("ban"))
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
        _audit_denied(message)
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


@router.message(Command("unban"))
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
        _audit_denied(message)
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
