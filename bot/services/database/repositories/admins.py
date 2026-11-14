# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Репозиторий обычных администраторов (без Supervisor)."""

import aiosqlite


async def get_admin_ids(connection: aiosqlite.Connection) -> set[int]:
    """Returns the IDs of all regular administrators."""
    cursor = await connection.execute(
        """
        SELECT user_id
        FROM admins
        ORDER BY user_id
        """
    )
    rows = await cursor.fetchall()
    return {row["user_id"] for row in rows}


async def add_admin(
    connection: aiosqlite.Connection,
    user_id: int,
) -> bool:
    """Adds an administrator; returns False if the user already was one."""
    cursor = await connection.execute(
        """
        INSERT OR IGNORE INTO admins(user_id)
        VALUES (?)
        """,
        (user_id,),
    )
    await connection.commit()
    return cursor.rowcount > 0


async def remove_admin(
    connection: aiosqlite.Connection,
    user_id: int,
) -> bool:
    """Removes an administrator; returns False if the user was not one."""
    cursor = await connection.execute(
        """
        DELETE FROM admins
        WHERE user_id = ?
        """,
        (user_id,),
    )
    await connection.commit()
    return cursor.rowcount > 0
