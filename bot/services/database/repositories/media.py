"""Репозиторий ссылок на медиафайлы в SQLite."""

import aiosqlite


async def fetch_old_media_rows(
    connection: aiosqlite.Connection,
    retention_days: int,
):
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
    cursor = await connection.execute("SELECT file_path FROM message_media")
    rows = await cursor.fetchall()
    return {row["file_path"] for row in rows if row["file_path"]}
