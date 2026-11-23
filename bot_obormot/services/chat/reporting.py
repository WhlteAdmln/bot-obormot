# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Safe reporting of results and errors to the user."""

import logging

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

_NOT_MODIFIED_DESCRIPTION = "message is not modified"

logger = logging.getLogger("bot_obormot.services.chat.reporting")


async def _edit_text(message: Message, text: str, parse_mode: str | None) -> None:
    """Edit the message text, omitting ``parse_mode`` when it is ``None``."""
    if parse_mode is None:
        await message.edit_text(text)
    else:
        await message.edit_text(text, parse_mode=parse_mode)


async def safe_edit(
    message: Message,
    text: str,
    parse_mode: str | None = ParseMode.HTML,
) -> None:
    """Safely edit a message.

    ``parse_mode=None`` edits the text without any formatting.
    """
    try:
        await _edit_text(message, text, parse_mode)
    except TelegramBadRequest as exc:
        if _NOT_MODIFIED_DESCRIPTION not in str(exc).lower():
            raise


async def report_error(
    message: Message,
    status: Message | None,
    text: str,
) -> None:
    """Safely report an error to the user."""
    if status is None:
        try:
            await message.answer(text)
        except Exception:
            logger.exception("Could not send error message")
        return

    try:
        await safe_edit(status, text)
    except Exception:
        logger.exception("Could not edit status message")
