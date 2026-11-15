# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Репозиторий блокировок пользователей."""

import aiosqlite


async def get_blocked_ids(connection: aiosqlite.Connection) -> set[int]:
    """Returns the IDs of all blocked users."""
    cursor = await connection.execute("SELECT user_id FROM blocked_users")
    rows = await cursor.fetchall()
    return {row["user_id"] for row in rows}


async def block_user(connection: aiosqlite.Connection, user_id: int) -> bool:
    """Blocks a user; returns False if the user was already blocked."""
    cursor = await connection.execute(
        "INSERT OR IGNORE INTO blocked_users(user_id) VALUES (?)", (user_id,)
    )
    await connection.commit()
    return cursor.rowcount > 0


async def unblock_user(connection: aiosqlite.Connection, user_id: int) -> bool:
    """Unblocks a user; returns False if the user was not blocked."""
    cursor = await connection.execute(
        "DELETE FROM blocked_users WHERE user_id = ?", (user_id,)
    )
    await connection.commit()
    return cursor.rowcount > 0
