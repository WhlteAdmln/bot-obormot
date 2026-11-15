# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Per-user locks that serialize chat requests."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_user_locks: dict[int, tuple[asyncio.Lock, int]] = {}


@asynccontextmanager
async def get_user_lock(user_id: int) -> AsyncIterator[None]:
    """Блокирует обработку сообщений пользователя и очищает неиспользуемый lock."""
    entry = _user_locks.get(user_id)

    if entry is None:
        lock = asyncio.Lock()
        users = 0
    else:
        lock, users = entry

    users += 1
    _user_locks[user_id] = (lock, users)

    acquired = False

    try:
        await lock.acquire()
        acquired = True
        yield
    finally:
        if acquired:
            lock.release()

        current_lock, current_users = _user_locks[user_id]
        remaining_users = current_users - 1

        if remaining_users == 0:
            _user_locks.pop(user_id, None)
        else:
            _user_locks[user_id] = (current_lock, remaining_users)


def pending_requests(user_id: int) -> int:
    """Число запросов пользователя, выполняющихся или ожидающих lock."""
    entry = _user_locks.get(user_id)
    return entry[1] if entry else 0
