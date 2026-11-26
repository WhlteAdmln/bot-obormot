# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation concurrency."""

import asyncio
import threading
from dataclasses import dataclass

import pytest

from bot_obormot.services.media.animation.concurrency import extract_with_limit
from tests.support.concurrency import ConcurrencyProbe


@pytest.mark.asyncio
async def test_extract_with_limit_returns_the_extractor_result() -> None:
    semaphore = asyncio.Semaphore(3)
    payload = b"\x00webm-chunk"

    def extractor(data: bytes, media_type: str) -> list[bytes]:
        return [data + media_type.encode("ascii")]

    result = await extract_with_limit(payload, "webm", extractor, semaphore)

    expected = [b"\x00webm-chunkwebm"]
    assert result == expected, "the extractor result must be returned unchanged"


@dataclass(frozen=True)
class _BlockedRun:
    reached_capacity: bool
    maximum: int
    results: list[list[bytes]]


@dataclass(frozen=True)
class _CancelledRun:
    second_started_while_held: bool
    first_cancelled: bool
    second_result: list[bytes]
    second_started: bool


async def _run_blocked(capacity: int, count: int) -> _BlockedRun:
    semaphore = asyncio.Semaphore(capacity)
    probe = ConcurrencyProbe()
    release = threading.Event()

    def extractor(data: bytes, _media_type: str) -> list[bytes]:
        with probe.running():
            if not release.wait(5):
                msg = "Extractor was not released"
                raise TimeoutError(msg)
            return [data]

    tasks = [
        asyncio.create_task(
            extract_with_limit(
                str(index).encode("ascii"),
                "gif",
                extractor,
                semaphore,
            )
        )
        for index in range(count)
    ]
    reached = await asyncio.to_thread(probe.wait_for_active, capacity, 2)
    release.set()
    results = await asyncio.gather(*tasks)
    return _BlockedRun(reached, probe.maximum, list(results))


async def _run_cancelled() -> _CancelledRun:
    semaphore = asyncio.Semaphore(1)
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()

    def first_extractor(data: bytes, _media_type: str) -> list[bytes]:
        first_started.set()
        if not release_first.wait(5):
            msg = "First extractor was not released"
            raise TimeoutError(msg)
        return [data]

    def second_extractor(data: bytes, _media_type: str) -> list[bytes]:
        second_started.set()
        return [data]

    first_task = asyncio.create_task(
        extract_with_limit(b"first", "gif", first_extractor, semaphore)
    )
    if not await asyncio.to_thread(first_started.wait, 2):
        msg = "First extractor did not start"
        raise TimeoutError(msg)

    first_task.cancel()
    second_task = asyncio.create_task(
        extract_with_limit(b"second", "gif", second_extractor, semaphore)
    )
    await asyncio.sleep(0)
    started_while_held = second_started.is_set()
    release_first.set()

    await asyncio.wait({first_task})
    second_result = await second_task
    return _CancelledRun(
        started_while_held,
        first_task.cancelled(),
        second_result,
        second_started.is_set(),
    )


@pytest.mark.asyncio
async def test_extract_with_limit_runs_up_to_the_capacity_at_once() -> None:
    run = await _run_blocked(capacity=2, count=4)

    assert run.reached_capacity is True, "the extractors did not fill the capacity"


@pytest.mark.asyncio
async def test_extract_with_limit_respects_semaphore_capacity() -> None:
    capacity = 2

    run = await _run_blocked(capacity=capacity, count=5)

    assert run.maximum == capacity, "more extractors ran at once than allowed"


@pytest.mark.asyncio
async def test_extract_with_limit_returns_the_results_in_task_order() -> None:
    run = await _run_blocked(capacity=3, count=4)

    expected = [[b"0"], [b"1"], [b"2"], [b"3"]]
    assert run.results == expected, "the results are out of order"


@pytest.mark.asyncio
async def test_cancelled_extractor_holds_semaphore_until_thread_finishes() -> None:
    run = await _run_cancelled()

    assert run.second_started_while_held is False, "the semaphore was released early"


@pytest.mark.asyncio
async def test_cancelled_extractor_task_ends_cancelled() -> None:
    run = await _run_cancelled()

    assert run.first_cancelled is True, "the cancelled task was not cancelled"


@pytest.mark.asyncio
async def test_extractor_after_a_cancelled_one_returns_its_result() -> None:
    run = await _run_cancelled()

    expected = [b"second"]
    assert run.second_result == expected, "the next extractor returned another result"


@pytest.mark.asyncio
async def test_extractor_after_a_cancelled_one_runs() -> None:
    run = await _run_cancelled()

    assert run.second_started is True, "the next extractor never ran"
