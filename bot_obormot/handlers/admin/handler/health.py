# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""The /health command and its component checks."""

import asyncio
import logging
from typing import TYPE_CHECKING, cast

from aiogram.types import Message

from bot_obormot.handlers.admin import texts
from bot_obormot.handlers.admin.handler.access import is_supervisor
from bot_obormot.services.audit import audit
from bot_obormot.services.database import Database
from bot_obormot.services.llm.client import LLMClient
from bot_obormot.settings import Settings

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger("bot_obormot.handlers.admin")


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
