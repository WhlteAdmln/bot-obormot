# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Concurrency limit for animation decoding."""

import asyncio
from collections.abc import Callable

from bot_obormot.services.media.animation.limits import MAX_CONCURRENT_ANIMATIONS

_animation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANIMATIONS)


async def extract_with_limit(
    data: bytes,
    media_type: str,
    extractor: Callable[[bytes, str], list[bytes]],
    semaphore: asyncio.Semaphore | None = None,
) -> list[bytes]:
    """Limit the number of concurrently processed animations."""
    active_semaphore = semaphore or _animation_semaphore

    async with active_semaphore:
        task = asyncio.create_task(asyncio.to_thread(extractor, data, media_type))

        try:
            return await asyncio.shield(task)

        except asyncio.CancelledError:
            # Cancelling the await does not stop the already running thread.
            # Wait for it to finish so the semaphore is not released
            # before processing has actually completed.
            try:
                await task
            finally:
                raise
