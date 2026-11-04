"""Совместимый путь импорта анимационного сервиса."""

import logging

from bot.errors import MediaError
from bot.services.media.animation import (
    MAX_CONCURRENT_ANIMATIONS,
    MAX_DIMENSION,
    MAX_DURATION,
    MAX_FRAMES,
    PROCESS_TIMEOUT,
    dispatch_extraction,
    image_to_bytes,
    extract_gif,
    extract_tgs,
    extract_video,
    sample_frame_indices,
)
from bot.services.media.animation import concurrency as _concurrency

logger = logging.getLogger("bot.services.animation")
_animation_semaphore = _concurrency._animation_semaphore

# Сохраняем старые внутренние имена для совместимости и тестовых подмен.
_image_to_bytes = image_to_bytes
_extract_gif = extract_gif
_extract_tgs = extract_tgs
_extract_webm = extract_video


def _extract_frames(data: bytes, media_type: str) -> list[bytes]:
    return dispatch_extraction(
        data,
        media_type,
        gif_extractor=_extract_gif,
        tgs_extractor=_extract_tgs,
        video_extractor=_extract_webm,
    )


async def _extract_with_limit(
    data: bytes,
    media_type: str,
) -> list[bytes]:
    return await _concurrency.extract_with_limit(
        data,
        media_type,
        _extract_frames,
        semaphore=_animation_semaphore,
    )


async def extract_animation_frames(
    data: bytes,
    media_type: str,
) -> list[bytes]:
    """Извлекает кадры и преобразует ошибки обработки в MediaError."""

    try:
        return await _extract_with_limit(data, media_type)
    except MediaError:
        raise
    except Exception as error:
        logger.exception(
            "Failed to extract animation frames: format=%s",
            media_type,
        )
        raise MediaError(f"Failed to process {media_type} animation") from error


__all__ = [
    "MAX_CONCURRENT_ANIMATIONS",
    "MAX_DIMENSION",
    "MAX_DURATION",
    "MAX_FRAMES",
    "PROCESS_TIMEOUT",
    "extract_animation_frames",
    "sample_frame_indices",
]
