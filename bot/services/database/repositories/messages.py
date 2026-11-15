# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Репозиторий сообщений и выборок истории."""

import sqlite3
from collections.abc import Iterable

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
) -> Iterable[sqlite3.Row]:
    """Возвращает строки полных обменов и связанные изображения."""
    cursor = await connection.execute(
        HISTORY_WITH_MEDIA,
        (user_id, exchange_limit, max_images),
    )
    return await cursor.fetchall()


async def fetch_user_media_paths(
    connection: aiosqlite.Connection,
    user_id: int,
) -> Iterable[sqlite3.Row]:
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


async def prune_user_history(
    connection: aiosqlite.Connection,
    user_id: int,
    keep_last_messages: int,
) -> list[str]:
    """Удаляет самые старые сообщения пользователя. Возвращает пути их картинок."""
    cursor = await connection.execute(
        """
        SELECT mm.file_path
        FROM message_media AS mm
        JOIN messages AS m ON m.id = mm.message_id
        WHERE m.user_id = ? AND m.id NOT IN (
            SELECT id FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (user_id, user_id, keep_last_messages),
    )
    paths = [row["file_path"] for row in await cursor.fetchall() if row["file_path"]]

    await connection.execute(
        """
        DELETE FROM messages
        WHERE user_id = ? AND id NOT IN (
            SELECT id FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
        )
        """,
        (user_id, user_id, keep_last_messages),
    )
    await connection.commit()

    return paths
