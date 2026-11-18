# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Extract frames from animations and videos."""

import logging

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import concurrency as _concurrency
from bot_obormot.services.media.animation.concurrency import _animation_semaphore
from bot_obormot.services.media.animation.dispatcher import dispatch_extraction
from bot_obormot.services.media.animation.gif import extract_gif
from bot_obormot.services.media.animation.jpeg import image_to_bytes
from bot_obormot.services.media.animation.limits import (
    MAX_CONCURRENT_ANIMATIONS,
    MAX_DIMENSION,
    MAX_DURATION,
    MAX_FRAMES,
    PROCESS_TIMEOUT,
)
from bot_obormot.services.media.animation.sampling import sample_frame_indices
from bot_obormot.services.media.animation.tgs import extract_tgs
from bot_obormot.services.media.animation.video import extract_video

logger = logging.getLogger("bot_obormot.services.media.animation")

# Preserve the previous internal names at the legacy import path.
_image_to_bytes = image_to_bytes
_extract_gif = extract_gif
_extract_tgs = extract_tgs
_extract_webm = extract_video


def _extract_frames(data: bytes, media_type: str) -> list[bytes]:
    """Compatibility dispatcher that preserves the legacy decoder patch points."""
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
    """Extract frames and convert processing errors to MediaError."""
    try:
        return await _extract_with_limit(data, media_type)

    except MediaError:
        raise

    except Exception as error:
        logger.exception(
            "Failed to extract animation frames: format=%s",
            media_type,
        )
        msg = f"Failed to process {media_type} animation"
        raise MediaError(msg) from error


__all__ = [
    "MAX_CONCURRENT_ANIMATIONS",
    "MAX_DIMENSION",
    "MAX_DURATION",
    "MAX_FRAMES",
    "PROCESS_TIMEOUT",
    "extract_animation_frames",
    "sample_frame_indices",
]
