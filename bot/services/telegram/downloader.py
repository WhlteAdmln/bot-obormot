"""Загрузка файлов через Telegram Bot API."""

import io
import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Message

from bot.errors import MediaError, TelegramError, TelegramFileTooBigError
from bot.services.telegram.constants import MAX_MEDIA_SIZE

# Сохраняем прежнее имя логгера, чтобы не менять маршрутизацию логов.
logger = logging.getLogger("bot.services.media")


async def download_telegram_file(message: Message, file_id: str) -> bytes:
    """Скачивает файл из Telegram с ограничением размера 20 МБ."""

    try:
        telegram_file = await message.bot.get_file(file_id)

        if telegram_file.file_size and telegram_file.file_size > MAX_MEDIA_SIZE:
            raise MediaError("Файл слишком большой (максимум 20 МБ).")

        buffer = io.BytesIO()

        await message.bot.download_file(
            telegram_file.file_path,
            destination=buffer,
        )

        data = buffer.getvalue()

    except TelegramBadRequest as error:
        if "file is too big" in str(error).lower():
            raise TelegramFileTooBigError(
                "Telegram cannot download this file because it is too large"
            ) from error

        logger.exception("Telegram rejected file download")
        raise TelegramError("Could not download file from Telegram") from error

    except TelegramAPIError as error:
        logger.exception("Failed to download file from Telegram")
        raise TelegramError("Could not download file from Telegram") from error

    if len(data) > MAX_MEDIA_SIZE:
        raise MediaError("Файл слишком большой (максимум 20 МБ).")

    return data
