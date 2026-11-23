# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories media."""

import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    media,
)
from tests.support.database_repositories import USER_ID


@pytest.mark.asyncio
async def test_media_repository_removes_only_old_media_references(
    test_db: Database,
) -> None:
    """Media repository removes only old media references."""
    cursor = await test_db.connection.execute(
        """
        INSERT INTO messages(user_id, role, content, created_at)
        VALUES (?, 'user', 'Старое сообщение', datetime('now', '-60 days'))
        """,
        (USER_ID,),
    )
    message_id = cursor.lastrowid
    await test_db.connection.execute(
        """
        INSERT INTO message_media(message_id, file_path, mime_type)
        VALUES (?, ?, 'image/jpeg')
        """,
        (message_id, "/data/images/old-image.jpg"),
    )
    await test_db.connection.commit()

    old_rows = await media.fetch_old_media_rows(test_db.connection, 30)
    assert [row["file_path"] for row in old_rows] == ["/data/images/old-image.jpg"]

    await media.delete_old_media_records(test_db.connection, 30)
    assert await media.fetch_referenced_media_paths(test_db.connection) == set()

    cursor = await test_db.connection.execute(
        "SELECT content FROM messages WHERE id = ?",
        (message_id,),
    )
    expected_content = "Старое сообщение"
    assert (await cursor.fetchone())["content"] == expected_content
