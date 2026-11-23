# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat locks."""

import asyncio

import pytest

from bot_obormot.services.chat import locks as chat_locks


@pytest.mark.asyncio
async def test_user_lock_serializes_same_user_and_releases_registry() -> None:
    """User lock serializes same user and releases registry."""
    first_inside = asyncio.Event()
    release_first = asyncio.Event()
    second_inside = asyncio.Event()

    async def first_worker() -> None:
        async with chat_locks.get_user_lock(202):
            first_inside.set()
            await release_first.wait()

    async def second_worker() -> None:
        async with chat_locks.get_user_lock(202):
            second_inside.set()

    first = asyncio.create_task(first_worker())
    await first_inside.wait()
    assert chat_locks.pending_requests(202) == 1
    second = asyncio.create_task(second_worker())
    await asyncio.sleep(0)
    assert not second_inside.is_set()
    expected_pending_requests = 2
    assert chat_locks.pending_requests(202) == expected_pending_requests

    release_first.set()
    await asyncio.gather(first, second)
    assert second_inside.is_set()
    assert chat_locks.pending_requests(202) == 0


@pytest.mark.asyncio
async def test_user_locks_allow_different_users_to_run_concurrently() -> None:
    """User locks allow different users to run concurrently."""
    async with chat_locks.get_user_lock(301), chat_locks.get_user_lock(302):
        inside = (chat_locks.pending_requests(301), chat_locks.pending_requests(302))
    expected = (1, 1)
    assert inside == expected, "both users must hold their own lock at once"


@pytest.mark.asyncio
async def test_user_lock_releases_after_exception() -> None:
    """User lock is released when the protected operation fails."""
    user_id = 303

    async def failing_request() -> None:
        async with chat_locks.get_user_lock(user_id):
            assert chat_locks.pending_requests(user_id) == 1
            msg = "request failed"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="request failed"):
        await failing_request()

    assert chat_locks.pending_requests(user_id) == 0

    async with chat_locks.get_user_lock(user_id):
        assert chat_locks.pending_requests(user_id) == 1

    assert chat_locks.pending_requests(user_id) == 0


@pytest.mark.asyncio
async def test_user_lock_cleans_registry_when_waiter_is_cancelled() -> None:
    """Cancelling a waiting request removes its lock registry entry."""
    user_id = 304
    owner_started = asyncio.Event()
    release_owner = asyncio.Event()

    async def owner() -> None:
        async with chat_locks.get_user_lock(user_id):
            owner_started.set()
            await release_owner.wait()

    async def waiter() -> None:
        async with chat_locks.get_user_lock(user_id):
            msg = "The waiter must not acquire the occupied lock."
            raise AssertionError(msg)

    owner_task = asyncio.create_task(owner())
    await owner_started.wait()

    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)

    expected_pending_requests = 2
    assert chat_locks.pending_requests(user_id) == expected_pending_requests

    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    assert chat_locks.pending_requests(user_id) == 1

    release_owner.set()
    await owner_task

    assert chat_locks.pending_requests(user_id) == 0
