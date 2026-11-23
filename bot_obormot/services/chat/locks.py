# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Per-user locks that serialize chat requests."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

_user_locks: dict[int, tuple[asyncio.Lock, int]] = {}


@contextmanager
def _registered(user_id: int) -> Iterator[asyncio.Lock]:
    """Count the user as active or waiting and drop the lock when unused."""
    entry = _user_locks.get(user_id)

    if entry is None:
        lock = asyncio.Lock()
        users = 0
    else:
        lock, users = entry

    users += 1
    _user_locks[user_id] = (lock, users)

    try:
        yield lock
    finally:
        current_lock, current_users = _user_locks[user_id]
        remaining_users = current_users - 1

        if remaining_users == 0:
            _user_locks.pop(user_id, None)
        else:
            _user_locks[user_id] = (current_lock, remaining_users)


@asynccontextmanager
async def _acquired(lock: asyncio.Lock) -> AsyncIterator[None]:
    """Hold the lock; a cancelled acquire never releases it."""
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()


@asynccontextmanager
async def get_user_lock(user_id: int) -> AsyncIterator[None]:
    """Serialize user message processing and clean up unused locks."""
    with _registered(user_id) as lock:
        async with _acquired(lock):
            yield


def pending_requests(user_id: int) -> int:
    """Return the number of active or waiting requests for a user."""
    entry = _user_locks.get(user_id)
    return entry[1] if entry else 0
