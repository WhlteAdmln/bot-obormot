# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Репозиторий ссылок на медиафайлы в SQLite."""

import sqlite3
from collections.abc import Iterable

import aiosqlite


async def fetch_old_media_rows(
    connection: aiosqlite.Connection,
    retention_days: int,
) -> Iterable[sqlite3.Row]:
    """Returns the media rows older than the retention period."""
    cursor = await connection.execute(
        """
        SELECT mm.id, mm.file_path
        FROM message_media AS mm
        JOIN messages AS m ON m.id = mm.message_id
        WHERE m.created_at < datetime('now', ?)
        """,
        (f"-{retention_days} days",),
    )
    return await cursor.fetchall()


async def delete_old_media_records(
    connection: aiosqlite.Connection,
    retention_days: int,
) -> None:
    """Deletes the media records older than the retention period."""
    await connection.execute(
        """
        DELETE FROM message_media
        WHERE id IN (
            SELECT mm.id
            FROM message_media AS mm
            JOIN messages AS m ON m.id = mm.message_id
            WHERE m.created_at < datetime('now', ?)
        )
        """,
        (f"-{retention_days} days",),
    )
    await connection.commit()


async def fetch_referenced_media_paths(
    connection: aiosqlite.Connection,
) -> set[str]:
    """Returns the file paths of all media referenced from the database."""
    cursor = await connection.execute("SELECT file_path FROM message_media")
    rows = await cursor.fetchall()
    return {row["file_path"] for row in rows if row["file_path"]}
