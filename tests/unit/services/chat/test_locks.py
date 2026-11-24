# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for UserLocks."""

import asyncio

import pytest

from bot_obormot.services.chat.locks import UserLocks


@pytest.fixture(name="user_locks")
def fixture_user_locks() -> UserLocks:
    """Return locks that no request has used yet."""
    return UserLocks()


async def _hold_until(
    user_locks: UserLocks,
    user_id: int,
    entered: asyncio.Event,
    release: asyncio.Event,
) -> None:
    async with user_locks.hold(user_id):
        entered.set()
        await release.wait()


async def _fail_inside(user_locks: UserLocks, user_id: int) -> None:
    async with user_locks.hold(user_id):
        msg = "model backend went away"
        raise RuntimeError(msg)


@pytest.mark.asyncio
async def test_counts_waiting_request_of_same_user(user_locks: UserLocks) -> None:
    user_id = 202
    entered = asyncio.Event()
    release = asyncio.Event()
    owner = asyncio.create_task(_hold_until(user_locks, user_id, entered, release))
    await entered.wait()
    waiter = asyncio.create_task(
        _hold_until(user_locks, user_id, asyncio.Event(), asyncio.Event())
    )
    await asyncio.sleep(0)

    pending = user_locks.pending(user_id)

    waiter.cancel()
    release.set()
    await asyncio.gather(owner, waiter, return_exceptions=True)
    expected_pending = 2
    assert pending == expected_pending, "the holder and the waiter must be counted"


@pytest.mark.asyncio
async def test_keeps_second_request_of_same_user_waiting(
    user_locks: UserLocks,
) -> None:
    user_id = 417
    first_entered = asyncio.Event()
    second_entered = asyncio.Event()
    release = asyncio.Event()
    first = asyncio.create_task(
        _hold_until(user_locks, user_id, first_entered, release)
    )
    await first_entered.wait()
    second = asyncio.create_task(
        _hold_until(user_locks, user_id, second_entered, release)
    )
    await asyncio.sleep(0)

    second_ran_early = second_entered.is_set()

    release.set()
    await asyncio.gather(first, second)
    assert second_ran_early is False, "a user must not run two requests at once"


@pytest.mark.asyncio
async def test_lets_different_users_hold_locks_at_once(
    user_locks: UserLocks,
) -> None:
    first_user = 301
    second_user = 30_299

    async with user_locks.hold(first_user), user_locks.hold(second_user):
        held = len(user_locks)

    expected_held = 2
    assert held == expected_held, "both users must hold their own lock at once"


@pytest.mark.asyncio
async def test_leaves_no_entry_after_request(user_locks: UserLocks) -> None:
    user_id = 8_812

    async with user_locks.hold(user_id):
        pass

    assert len(user_locks) == 0, "a finished request must not leave a lock behind"


@pytest.mark.asyncio
async def test_leaves_no_entry_after_failed_request(user_locks: UserLocks) -> None:
    user_id = 303

    with pytest.raises(RuntimeError, match="model backend went away"):
        await _fail_inside(user_locks, user_id)

    assert len(user_locks) == 0, "a failed request must not leave a lock behind"


@pytest.mark.asyncio
async def test_releases_lock_after_failed_request(user_locks: UserLocks) -> None:
    user_id = 5_150
    with pytest.raises(RuntimeError, match="model backend went away"):
        await _fail_inside(user_locks, user_id)

    async with asyncio.timeout(1), user_locks.hold(user_id):
        pending = user_locks.pending(user_id)

    assert pending == 1, "the next request must get the lock after a failure"


@pytest.mark.asyncio
async def test_drops_cancelled_waiter_from_pending(user_locks: UserLocks) -> None:
    user_id = 304
    entered = asyncio.Event()
    release = asyncio.Event()
    owner = asyncio.create_task(_hold_until(user_locks, user_id, entered, release))
    await entered.wait()
    waiter = asyncio.create_task(
        _hold_until(user_locks, user_id, asyncio.Event(), asyncio.Event())
    )
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)

    pending = user_locks.pending(user_id)

    release.set()
    await owner
    assert pending == 1, "a cancelled waiter must not stay counted"


@pytest.mark.asyncio
async def test_leaves_no_entry_after_cancelled_waiter(
    user_locks: UserLocks,
) -> None:
    user_id = 7_723
    entered = asyncio.Event()
    release = asyncio.Event()
    owner = asyncio.create_task(_hold_until(user_locks, user_id, entered, release))
    await entered.wait()
    waiter = asyncio.create_task(
        _hold_until(user_locks, user_id, asyncio.Event(), asyncio.Event())
    )
    await asyncio.sleep(0)
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    release.set()
    await owner

    assert len(user_locks) == 0, "a cancelled waiter must not leave a lock behind"


def test_reports_no_pending_requests_for_unknown_user(
    user_locks: UserLocks,
) -> None:
    user_id = 99_001

    pending = user_locks.pending(user_id)

    assert pending == 0, "a user without requests must have none pending"
