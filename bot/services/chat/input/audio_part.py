"""Подготовка аудио и получение распознанного текста."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from bot.services.chat.input.models import MessageInfo

if TYPE_CHECKING:
    from aiogram.types import Message

logger = logging.getLogger("bot.services.chat.input.audio_part")


async def prepare_audio(
    message: Message,
    info: MessageInfo,
    *,
    duration_validator: Callable | None = None,
    downloader: Callable | None = None,
    transcriber: Callable[..., Awaitable[str]] | None = None,
) -> str:
    """Скачивает аудио и возвращает результат распознавания Whisper."""

    if duration_validator is None:
        from bot.services.audio import validate_audio_duration

        duration_validator = validate_audio_duration

    if downloader is None:
        from bot.services.telegram.downloader import download_telegram_file

        downloader = download_telegram_file

    if transcriber is None:
        from bot.services.audio import transcribe_audio

        transcriber = transcribe_audio

    duration_validator(message)

    logger.info("AUDIO: начинаю скачивание из Telegram")

    audio_data = await downloader(
        message,
        info.audio_file_id,
    )

    logger.info(
        "AUDIO: файл скачан, размер: %s байт",
        len(audio_data),
    )

    logger.info("AUDIO: отправляю файл на Whisper")

    transcribed_text = await transcriber(
        audio_data,
        info.audio_filename,
    )

    logger.info("AUDIO: распознано символов: %d", len(transcribed_text))

    return transcribed_text
