# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Совместимый фасад для обработки Telegram-медиа."""

import logging

from aiogram.types import Message

from bot.services.media import pipeline as _pipeline
from bot.services.media.animation import extract_animation_frames
from bot.services.media.content import get_user_content
from bot.services.media.detection import get_media_info
from bot.services.media.images import prepare_image
from bot.services.media.limits import MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS
from bot.services.media.prompts import get_media_prompt
from bot.services.telegram.constants import MAX_MEDIA_SIZE
from bot.services.telegram.downloader import download_telegram_file

logger = logging.getLogger("bot.services.media")


async def process_media(
    message: Message,
    media_type: str,
    file_id: str,
) -> list[str]:
    """Скачивает и обрабатывает медиа через отдельный pipeline."""
    return await _pipeline.process_media(
        message,
        media_type,
        file_id,
        options=_pipeline.MediaPipelineOptions(
            downloader=download_telegram_file,
            animation_extractor=extract_animation_frames,
            image_preparer=prepare_image,
        ),
    )


__all__ = [
    "MAX_IMAGE_DIMENSION",
    "MAX_IMAGE_PIXELS",
    "MAX_MEDIA_SIZE",
    "download_telegram_file",
    "extract_animation_frames",
    "get_media_info",
    "get_media_prompt",
    "get_user_content",
    "logger",
    "prepare_image",
    "process_media",
]
