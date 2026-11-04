"""Загрузка файлов через Telegram Bot API."""

import asyncio
import io
import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Message

from bot.errors import MediaError, TelegramError, TelegramFileTooBigError
from bot.services.telegram.constants import MAX_CONCURRENT_DOWNLOADS, MAX_MEDIA_SIZE

# Не допускаем одновременного накопления большого числа файлов в памяти.
_download_slots = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

# Сохраняем прежнее имя логгера, чтобы не менять маршрутизацию логов.
logger = logging.getLogger("bot.services.media")


class _LimitedBytesIO(io.BytesIO):
    """Буфер, который не позволяет записать больше заданного числа байт."""

    def __init__(self, limit: int) -> None:
        super().__init__()
        self._limit = limit

    def write(self, data: bytes) -> int:
        if len(data) > self._limit - self.tell():
            raise MediaError("Файл слишком большой (максимум 20 МБ).")

        return super().write(data)


async def download_telegram_file(message: Message, file_id: str) -> bytes:
    """Скачивает файл из Telegram с ограничением размера 20 МБ."""

    try:
        telegram_file = await message.bot.get_file(file_id)
        file_size = telegram_file.file_size

        if (
            not isinstance(file_size, int)
            or isinstance(file_size, bool)
            or file_size <= 0
        ):
            raise MediaError("Не удалось определить размер файла.")

        if file_size > MAX_MEDIA_SIZE:
            raise MediaError("Файл слишком большой (максимум 20 МБ).")

        async with _download_slots:
            buffer = _LimitedBytesIO(MAX_MEDIA_SIZE)
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
