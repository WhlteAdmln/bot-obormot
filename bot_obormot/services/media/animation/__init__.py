# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Extract frames from animations and videos."""

import logging

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import concurrency as _concurrency
from bot_obormot.services.media.animation.concurrency import _animation_semaphore
from bot_obormot.services.media.animation.dispatcher import dispatch_extraction
from bot_obormot.services.media.animation.limits import (
    MAX_CONCURRENT_ANIMATIONS,
    MAX_DIMENSION,
    MAX_DURATION,
    MAX_FRAMES,
    PROCESS_TIMEOUT,
)
from bot_obormot.services.media.animation.sampling import sample_frame_indices

logger = logging.getLogger("bot_obormot.services.media.animation")


async def extract_animation_frames(
    data: bytes,
    media_type: str,
) -> list[bytes]:
    """Extract frames and convert processing errors to MediaError."""
    try:
        return await _concurrency.extract_with_limit(
            data,
            media_type,
            dispatch_extraction,
            semaphore=_animation_semaphore,
        )

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
