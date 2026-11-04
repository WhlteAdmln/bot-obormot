"""Репозиторий блокировок пользователей."""

import aiosqlite


async def get_blocked_ids(connection: aiosqlite.Connection) -> set[int]:
    cursor = await connection.execute("SELECT user_id FROM blocked_users")
    rows = await cursor.fetchall()
    return {row["user_id"] for row in rows}


async def block_user(connection: aiosqlite.Connection, user_id: int) -> bool:
    cursor = await connection.execute(
        "INSERT OR IGNORE INTO blocked_users(user_id) VALUES (?)", (user_id,)
    )
    await connection.commit()
    return cursor.rowcount > 0


async def unblock_user(connection: aiosqlite.Connection, user_id: int) -> bool:
    cursor = await connection.execute(
        "DELETE FROM blocked_users WHERE user_id = ?", (user_id,)
    )
    await connection.commit()
    return cursor.rowcount > 0
