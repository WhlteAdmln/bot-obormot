# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories media."""

import aiosqlite
import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    media,
)


@pytest.fixture(name="connection")
def fixture_connection(test_db: Database) -> aiosqlite.Connection:
    """Return the open connection of the test database."""
    if test_db.connection is None:
        message = "the test database has no open connection"
        raise RuntimeError(message)
    return test_db.connection


async def _insert_old_message_with_media(
    connection: aiosqlite.Connection,
    user_id: int,
    content: str,
    file_path: str,
) -> int:
    cursor = await connection.execute(
        """
        INSERT INTO messages(user_id, role, content, created_at)
        VALUES (?, 'user', ?, datetime('now', '-60 days'))
        """,
        (user_id, content),
    )
    message_id = cursor.lastrowid
    if message_id is None:
        message = "the inserted message has no id"
        raise RuntimeError(message)
    await connection.execute(
        """
        INSERT INTO message_media(message_id, file_path, mime_type)
        VALUES (?, ?, 'image/jpeg')
        """,
        (message_id, file_path),
    )
    await connection.commit()
    return message_id


@pytest.mark.asyncio
async def test_fetch_old_media_rows_returns_old_media(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 5551234
    file_path = "/data/images/old-image.jpg"
    await _insert_old_message_with_media(
        connection, user_id, "Старое сообщение", file_path
    )
    old_rows = await media.fetch_old_media_rows(connection, 30)
    expected_paths = [file_path]
    paths = [row["file_path"] for row in old_rows]
    assert paths == expected_paths, "the old media rows differ"


@pytest.mark.asyncio
async def test_delete_old_media_records_removes_media_references(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 8675309
    file_path = "/data/images/2025/cat-photo.png"
    await _insert_old_message_with_media(connection, user_id, "Фото кота", file_path)
    await media.delete_old_media_records(connection, 30)
    expected_empty: set[str] = set()
    paths = await media.fetch_referenced_media_paths(connection)
    assert paths == expected_empty, "an old media reference is still stored"


@pytest.mark.asyncio
async def test_delete_old_media_records_keeps_the_message(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 4242
    expected_content = "Сообщение с картинкой"
    message_id = await _insert_old_message_with_media(
        connection, user_id, expected_content, "/data/images/scan-01.jpg"
    )
    await media.delete_old_media_records(connection, 30)
    cursor = await connection.execute(
        "SELECT content FROM messages WHERE id = ?",
        (message_id,),
    )
    row = await cursor.fetchone()
    content = None if row is None else row["content"]
    assert content == expected_content, "the message of the old media was changed"
