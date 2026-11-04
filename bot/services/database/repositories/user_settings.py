"""Репозиторий персональных системных промптов."""

import aiosqlite


async def get_system_prompt(
    connection: aiosqlite.Connection,
    user_id: int,
) -> str | None:
    cursor = await connection.execute(
        """
        SELECT system_prompt
        FROM user_settings
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = await cursor.fetchone()
    return row["system_prompt"] if row else None


async def delete_system_prompt(
    connection: aiosqlite.Connection,
    user_id: int,
) -> None:
    await connection.execute(
        """
        DELETE FROM user_settings
        WHERE user_id = ?
        """,
        (user_id,),
    )
    await connection.commit()


async def set_system_prompt(
    connection: aiosqlite.Connection,
    user_id: int,
    prompt: str,
) -> None:
    await connection.execute(
        """
        INSERT INTO user_settings(user_id, system_prompt)
        VALUES (?, ?)
        ON CONFLICT(user_id)
        DO UPDATE SET system_prompt = excluded.system_prompt
        """,
        (user_id, prompt),
    )
    await connection.commit()
