# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Репозиторий индивидуальных лимитов истории."""

import aiosqlite


async def get_history_limit(
    connection: aiosqlite.Connection,
    user_id: int,
) -> int | None:
    """Returns the individual history limit of the user, if one is set."""
    cursor = await connection.execute(
        """
        SELECT exchange_limit
        FROM user_history_limits
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = await cursor.fetchone()
    return row["exchange_limit"] if row is not None else None


async def set_history_limit(
    connection: aiosqlite.Connection,
    user_id: int,
    exchange_limit: int,
) -> None:
    """Stores the individual history limit of the user."""
    await connection.execute(
        """
        INSERT INTO user_history_limits(user_id, exchange_limit)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET exchange_limit = excluded.exchange_limit
        """,
        (user_id, exchange_limit),
    )
    await connection.commit()


async def delete_history_limit(
    connection: aiosqlite.Connection,
    user_id: int,
) -> None:
    """Deletes the individual history limit of the user."""
    await connection.execute(
        """
        DELETE FROM user_history_limits
        WHERE user_id = ?
        """,
        (user_id,),
    )
    await connection.commit()
