# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation concurrency."""

import asyncio
import threading

import pytest

from bot_obormot.services.media.animation.concurrency import extract_with_limit


@pytest.mark.asyncio
async def test_extract_with_limit_uses_default_semaphore() -> None:
    """Use the module semaphore when no explicit semaphore is supplied."""

    def extractor(data: bytes, media_type: str) -> list[bytes]:
        return [data + media_type.encode("ascii")]

    result = await extract_with_limit(b"data", "gif", extractor)

    assert result == [b"datagif"]


@pytest.mark.asyncio
async def test_extract_with_limit_respects_semaphore_capacity() -> None:
    """Keep the number of concurrent extractors within semaphore capacity."""
    semaphore = asyncio.Semaphore(2)
    guard = threading.Lock()
    both_started = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0

    def extractor(data: bytes, _media_type: str) -> list[bytes]:
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                both_started.set()
        try:
            if not release.wait(5):
                msg = "Extractor was not released"
                raise TimeoutError(msg)
            return [data]
        finally:
            with guard:
                active -= 1

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

    assert await asyncio.to_thread(both_started.wait, 2)
    assert maximum == 2
    release.set()

    results = await asyncio.gather(*tasks)

    assert results == [[b"0"], [b"1"], [b"2"], [b"3"]]
    assert maximum == 2


@pytest.mark.asyncio
async def test_cancelled_extractor_holds_semaphore_until_thread_finishes() -> None:
    """Do not release the semaphore while a cancelled worker is still running."""
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
