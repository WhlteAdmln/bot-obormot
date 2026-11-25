# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Compatible facade for processing Telegram media."""

import logging

from aiogram.types import Message

from bot_obormot.services.media import pipeline as _pipeline
from bot_obormot.services.media.animation import extract_animation_frames
from bot_obormot.services.media.content import get_user_content
from bot_obormot.services.media.detection import get_media_info
from bot_obormot.services.media.images import prepare_image
from bot_obormot.services.media.limits import MAX_IMAGE_DIMENSION, MAX_IMAGE_PIXELS
from bot_obormot.services.media.prompts import get_media_prompt
from bot_obormot.services.media.slots import MediaSlots
from bot_obormot.services.telegram.constants import MAX_MEDIA_SIZE

logger = logging.getLogger("bot_obormot.services.media")


async def process_media(
    message: Message,
    media_type: str,
    file_id: str,
    *,
    downloader: _pipeline.Downloader,
    slots: MediaSlots,
) -> list[str]:
    """Download and process media through a dedicated pipeline."""
    return await _pipeline.process_media(
        message,
        media_type,
        file_id,
        options=_pipeline.MediaPipelineOptions(
            downloader=downloader,
            slots=slots,
            animation_extractor=extract_animation_frames,
            image_preparer=prepare_image,
        ),
    )


__all__ = [
    "MAX_IMAGE_DIMENSION",
    "MAX_IMAGE_PIXELS",
    "MAX_MEDIA_SIZE",
    "MediaSlots",
    "extract_animation_frames",
    "get_media_info",
    "get_media_prompt",
    "get_user_content",
    "logger",
    "prepare_image",
    "process_media",
]
