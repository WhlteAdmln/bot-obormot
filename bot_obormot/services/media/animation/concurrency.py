# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Concurrency limit for animation decoding."""

import asyncio
from collections.abc import Callable

from bot_obormot.services.media.animation.limits import MAX_CONCURRENT_ANIMATIONS
from bot_obormot.services.media.limited import run_limited

_animation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANIMATIONS)


async def extract_with_limit(
    data: bytes,
    media_type: str,
    extractor: Callable[[bytes, str], list[bytes]],
    semaphore: asyncio.Semaphore | None = None,
) -> list[bytes]:
    """Limit the number of concurrently processed animations."""
    active_semaphore = semaphore or _animation_semaphore

    return await run_limited(active_semaphore, extractor, data, media_type)
