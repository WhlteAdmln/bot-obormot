# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation concurrency."""

import asyncio
import threading

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


@pytest.mark.asyncio
async def test_extract_with_limit_respects_semaphore_capacity() -> None:
    semaphore = asyncio.Semaphore(2)
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
        for index in range(4)
    ]

    assert await asyncio.to_thread(probe.wait_for_active, 2, 2)
    expected_maximum = 2
    assert probe.maximum == expected_maximum
    release.set()

    results = await asyncio.gather(*tasks)

    assert results == [[b"0"], [b"1"], [b"2"], [b"3"]]
    expected_maximum = 2
    assert probe.maximum == expected_maximum


@pytest.mark.asyncio
async def test_cancelled_extractor_holds_semaphore_until_thread_finishes() -> None:
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
    assert await asyncio.to_thread(first_started.wait, 2)

    first_task.cancel()
    second_task = asyncio.create_task(
        extract_with_limit(b"second", "gif", second_extractor, semaphore)
    )
    await asyncio.sleep(0)

    assert not second_started.is_set()
    release_first.set()

    with pytest.raises(asyncio.CancelledError):
        await first_task

    assert await second_task == [b"second"]
    assert second_started.is_set()
