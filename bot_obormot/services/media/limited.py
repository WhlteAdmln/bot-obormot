# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Run blocking media work in a worker thread under a concurrency limit."""

import asyncio
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")


async def run_limited(
    semaphore: asyncio.Semaphore,
    func: Callable[..., _T],
    *args: object,
) -> _T:
    """Run ``func`` in a thread while holding one slot of ``semaphore``.

    A thread cannot be cancelled, so a cancelled caller keeps the slot until the
    thread has finished; the semaphore therefore never under-counts running work.
    """
    async with semaphore:
        task = asyncio.create_task(asyncio.to_thread(func, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            finally:
                raise
