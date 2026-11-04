"""Репозиторий обычных администраторов (без Supervisor)."""

import aiosqlite


async def get_admin_ids(connection: aiosqlite.Connection) -> set[int]:
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
    cursor = await connection.execute(
        """
        DELETE FROM admins
        WHERE user_id = ?
        """,
        (user_id,),
    )
    await connection.commit()
    return cursor.rowcount > 0
