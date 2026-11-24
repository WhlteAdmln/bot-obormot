# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the thread concurrency limit of media work."""

import asyncio
import threading

import pytest

from bot_obormot.services.media.limited import run_limited
from tests.support.concurrency import ConcurrencyProbe


@pytest.mark.asyncio
async def test_run_limited_caps_concurrent_jobs_at_the_semaphore_size() -> None:
    probe = ConcurrencyProbe()
    semaphore = asyncio.Semaphore(2)
    pair = threading.Barrier(2, timeout=5)

    def work(value: int) -> int:
        with probe.running():
            pair.wait()
            return value

    await asyncio.gather(*(run_limited(semaphore, work, value) for value in range(6)))
    expected = 2
    assert probe.maximum == expected, "no more than two jobs may run at once"


@pytest.mark.asyncio
async def test_run_limited_returns_every_result_in_order() -> None:
    semaphore = asyncio.Semaphore(3)
    values = [5, -2, 17, 0, 9]
    results = await asyncio.gather(
        *(run_limited(semaphore, abs, value) for value in values)
    )
    expected = [5, 2, 17, 0, 9]
    assert results == expected, "results must follow the call order"
