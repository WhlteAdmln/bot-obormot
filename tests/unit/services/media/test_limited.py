# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the thread concurrency limit of media work."""

import asyncio
import threading

import pytest

from bot_obormot.services.media.limited import run_limited
from tests.support.concurrency import ConcurrencyProbe


def _raise_value_error(text: str) -> int:
    raise ValueError(text)


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


@pytest.mark.asyncio
async def test_run_limited_releases_the_slot_after_a_failing_job() -> None:
    semaphore = asyncio.Semaphore(1)
    with pytest.raises(ValueError, match="corrupt frame"):
        await run_limited(semaphore, _raise_value_error, "corrupt frame")
    result = await run_limited(semaphore, len, "after-failure")
    expected = 13
    assert result == expected, "a failed job must not keep its slot"


@pytest.mark.asyncio
async def test_run_limited_keeps_the_slot_until_a_cancelled_job_ends() -> None:
    probe = ConcurrencyProbe()
    semaphore = asyncio.Semaphore(1)
    release = threading.Event()

    def blocked() -> None:
        with probe.running():
            release.wait(timeout=5)

    first = asyncio.create_task(run_limited(semaphore, blocked))
    await asyncio.to_thread(probe.wait_for_active, 1, 5)
    first.cancel()
    second = asyncio.create_task(run_limited(semaphore, blocked))
    locked_while_cancelled = semaphore.locked()
    release.set()
    await asyncio.gather(first, second, return_exceptions=True)
    observed = (locked_while_cancelled, probe.maximum)
    expected = (True, 1)
    assert observed == expected, "a cancelled job must hold its slot until it ends"
