"""Репозиторий сообщений и выборок истории."""

import aiosqlite

from bot.services.database.queries.history import HISTORY_WITH_MEDIA


async def add_message(
    connection: aiosqlite.Connection,
    user_id: int,
    role: str,
    content: str,
) -> None:
    """Добавляет отдельное сообщение и фиксирует изменение."""
    await connection.execute(
        """
        INSERT INTO messages(user_id, role, content)
        VALUES (?, ?, ?)
        """,
        (user_id, role, content),
    )
    await connection.commit()


async def fetch_history_rows(
    connection: aiosqlite.Connection,
    user_id: int,
    exchange_limit: int,
    max_images: int,
):
    """Возвращает строки полных обменов и связанные изображения."""
    cursor = await connection.execute(
        HISTORY_WITH_MEDIA,
        (user_id, exchange_limit, max_images),
    )
    return await cursor.fetchall()


async def fetch_user_media_paths(
    connection: aiosqlite.Connection,
    user_id: int,
):
    """Возвращает пути изображений, связанных с сообщениями пользователя."""
    cursor = await connection.execute(
        """
        SELECT mm.file_path
        FROM message_media mm
        JOIN messages m ON m.id = mm.message_id
        WHERE m.user_id = ?
        """,
        (user_id,),
    )
    return await cursor.fetchall()


async def delete_user_messages(
    connection: aiosqlite.Connection,
    user_id: int,
) -> None:
    """Удаляет сообщения пользователя и фиксирует изменение."""
    await connection.execute(
        "DELETE FROM messages WHERE user_id = ?",
        (user_id,),
    )
    await connection.commit()
