# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Per-user locks that serialize chat requests."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager


@asynccontextmanager
async def _acquired(lock: asyncio.Lock) -> AsyncIterator[None]:
    """Hold the lock; a cancelled acquire never releases it."""
    await lock.acquire()
    try:
        yield
    finally:
        lock.release()


class UserLocks:
    """Serialize the requests of each user and keep only locks in use."""

    def __init__(self) -> None:
        """Start without locks."""
        self._entries: dict[int, tuple[asyncio.Lock, int]] = {}

    def __len__(self) -> int:
        """Return the number of users with an active or waiting request."""
        return len(self._entries)

    def pending(self, user_id: int) -> int:
        """Return the number of active or waiting requests for a user."""
        entry = self._entries.get(user_id)
        return entry[1] if entry else 0

    @asynccontextmanager
    async def hold(self, user_id: int) -> AsyncIterator[None]:
        """Serialize user message processing and clean up unused locks."""
        with self._registered(user_id) as lock:
            async with _acquired(lock):
                yield

    @contextmanager
    def _registered(self, user_id: int) -> Iterator[asyncio.Lock]:
        """Count the user as active or waiting and drop the lock when unused."""
        entry = self._entries.get(user_id)

        if entry is None:
            lock = asyncio.Lock()
            users = 0
        else:
            lock, users = entry

        users += 1
        self._entries[user_id] = (lock, users)

        try:
            yield lock
        finally:
            current_lock, current_users = self._entries[user_id]
            remaining_users = current_users - 1

            if remaining_users == 0:
                self._entries.pop(user_id, None)
            else:
                self._entries[user_id] = (current_lock, remaining_users)
