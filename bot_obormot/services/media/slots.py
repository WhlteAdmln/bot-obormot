# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Concurrency limits for media processing of one running bot."""

import asyncio
from dataclasses import dataclass, field
from functools import partial

from bot_obormot.services.media.animation.limits import MAX_CONCURRENT_ANIMATIONS
from bot_obormot.services.media.limits import MAX_CONCURRENT_IMAGE_JOBS


@dataclass(frozen=True)
class MediaSlots:
    """Limit how many images and animations are processed at the same time.

    Create one instance per running bot: each semaphore binds to the event loop
    in which a job first has to wait for a free slot.
    """

    image_jobs: asyncio.Semaphore = field(
        default_factory=partial(asyncio.Semaphore, MAX_CONCURRENT_IMAGE_JOBS)
    )
    animations: asyncio.Semaphore = field(
        default_factory=partial(asyncio.Semaphore, MAX_CONCURRENT_ANIMATIONS)
    )
