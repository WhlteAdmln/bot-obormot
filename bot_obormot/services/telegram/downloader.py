# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Download files through the Telegram Bot API."""

import asyncio
import io
import logging
from typing import TYPE_CHECKING, cast

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Message

if TYPE_CHECKING:
    from aiogram import Bot

from bot_obormot.errors import MediaError, TelegramError, TelegramFileTooBigError
from bot_obormot.services.telegram.constants import (
    MAX_CONCURRENT_DOWNLOADS,
    MAX_MEDIA_SIZE,
)
from bot_obormot.services.telegram.texts import (
    TELEGRAM_FILE_SIZE_UNKNOWN,
    TELEGRAM_FILE_TOO_LARGE,
)

_FILE_TOO_BIG_DESCRIPTION = "file is too big"

# Prevent too many large files from accumulating in memory at once.
_download_slots = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# Preserve the previous logger name to avoid changing log routing.
logger = logging.getLogger("bot_obormot.services.media")


class _LimitedBytesIO(io.BytesIO):
    """A buffer that prevents writes beyond the configured byte limit."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit

    def write(self, data: object) -> int:
        view = memoryview(cast("bytes | bytearray | memoryview", data))
        if view.nbytes > self._limit - self.tell():
            msg = TELEGRAM_FILE_TOO_LARGE
            raise MediaError(msg)

        return super().write(view)


async def _fetch_file(bot: "Bot", file_id: str) -> bytes:
    """Check the declared size, then download the file into a limited buffer."""
    telegram_file = await bot.get_file(file_id)
    file_size = telegram_file.file_size

    if not isinstance(file_size, int) or isinstance(file_size, bool) or file_size <= 0:
        msg = TELEGRAM_FILE_SIZE_UNKNOWN
        raise MediaError(msg)

    if file_size > MAX_MEDIA_SIZE:
        msg = TELEGRAM_FILE_TOO_LARGE
        raise MediaError(msg)

    async with _download_slots:
        buffer = _LimitedBytesIO(MAX_MEDIA_SIZE)
        await bot.download_file(
            cast("str", telegram_file.file_path),
            destination=buffer,
        )
        return buffer.getvalue()


async def download_telegram_file(message: Message, file_id: str) -> bytes:
    """Download a file from Telegram with a 20 MB size limit."""
    bot = cast("Bot", message.bot)
    try:
        data = await _fetch_file(bot, file_id)

    except TelegramBadRequest as error:
        if _FILE_TOO_BIG_DESCRIPTION in str(error).lower():
            msg = "Telegram cannot download this file because it is too large"
            raise TelegramFileTooBigError(msg) from error

        logger.exception("Telegram rejected file download")
        msg = "Could not download file from Telegram"
        raise TelegramError(msg) from error

    except TelegramAPIError as error:
        logger.exception("Failed to download file from Telegram")
        msg = "Could not download file from Telegram"
        raise TelegramError(msg) from error

    if len(data) > MAX_MEDIA_SIZE:
        msg = TELEGRAM_FILE_TOO_LARGE
        raise MediaError(msg)

    return data
