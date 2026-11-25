# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Concurrency limit for animation decoding."""

import asyncio
from collections.abc import Callable

from bot_obormot.services.media.limited import run_limited


async def extract_with_limit(
    data: bytes,
    media_type: str,
    extractor: Callable[[bytes, str], list[bytes]],
    semaphore: asyncio.Semaphore,
) -> list[bytes]:
    """Limit the number of concurrently processed animations."""
    return await run_limited(semaphore, extractor, data, media_type)
