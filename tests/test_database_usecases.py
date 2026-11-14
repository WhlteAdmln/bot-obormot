# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database usecases."""

import logging
import os
import time
import uuid
from pathlib import Path

import pytest

from bot.errors import DatabaseError
from bot.services.database import Database
from bot.services.database.usecases import cleanup as cleanup_usecase

USER_ID = 616161


@pytest.mark.asyncio
async def test_add_exchange_rolls_back_database_and_removes_saved_images(
    test_db: Database,
) -> None:
    """Add exchange rolls back database and removes saved images."""
    await test_db.connection.execute(
        """
        CREATE TRIGGER reject_assistant_message
        BEFORE INSERT ON messages
        WHEN NEW.role = 'assistant'
        BEGIN
            SELECT RAISE(ABORT, 'blocked for test');
        END;
        """
    )
    await test_db.connection.commit()

    with pytest.raises(DatabaseError, match="Could not save message exchange"):
        await test_db.add_exchange(
            USER_ID,
            "Вопрос",
            "Ответ",
            media=[b"image-bytes"],
        )

    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM messages WHERE user_id = ?",
        (USER_ID,),
    )
    assert (await cursor.fetchone())["total"] == 0

    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM message_media"
    )
    assert (await cursor.fetchone())["total"] == 0
    assert list(test_db.images_dir.iterdir()) == []
    # Успешный следующий запрос доказывает, что lock был освобождён.
    assert await test_db.health_check() is True


@pytest.mark.asyncio
async def test_cleanup_usecase_removes_only_expired_orphan_images(
    test_db: Database,
) -> None:
    """Cleanup usecase removes only expired orphan images."""
    expired_orphan = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    recent_orphan = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    non_managed_file = test_db.images_dir / "readme.txt"
    expired_orphan.write_bytes(b"expired")
    recent_orphan.write_bytes(b"recent")
    non_managed_file.write_text("keep this file", encoding="utf-8")
    old_time = time.time() - 48 * 60 * 60
    os.utime(expired_orphan, (old_time, old_time))

    result = await cleanup_usecase.cleanup_old_images(
        test_db.connection,
        test_db.images_dir,
        retention_days=30,
        orphan_grace_hours=24,
        logger=logging.getLogger(__name__),
    )

    assert result == {"old_images": 0, "orphan_images": 1, "failed": 0}
    assert not expired_orphan.exists()
    assert recent_orphan.exists()
    assert non_managed_file.read_text(encoding="utf-8") == "keep this file"


@pytest.mark.asyncio
async def test_cleanup_usecase_rejects_invalid_retention_values(
    test_db: Database,
) -> None:
    """Cleanup usecase rejects invalid retention values."""
    with pytest.raises(ValueError, match="retention_days"):
        await cleanup_usecase.cleanup_old_images(
            test_db.connection,
            test_db.images_dir,
            retention_days=0,
            orphan_grace_hours=24,
            logger=logging.getLogger(__name__),
        )

    with pytest.raises(ValueError, match="orphan_grace_hours"):
        await cleanup_usecase.cleanup_old_images(
            test_db.connection,
            test_db.images_dir,
            retention_days=30,
            orphan_grace_hours=0,
            logger=logging.getLogger(__name__),
        )


@pytest.mark.asyncio
async def test_cleanup_skips_old_image_outside_managed_directory(
    test_db: Database, tmp_path: Path
) -> None:
    """Cleanup skips old image outside managed directory."""
    external_image = tmp_path.parent / "external-old-image.jpg"
    external_image.write_bytes(b"do-not-delete")
    cursor = await test_db.connection.execute(
        """
        INSERT INTO messages(user_id, role, content, created_at)
        VALUES (?, 'user', 'Старый текст', datetime('now', '-60 days'))
        """,
        (USER_ID,),
    )
    message_id = cursor.lastrowid
    await test_db.connection.execute(
        """
        INSERT INTO message_media(message_id, file_path, mime_type)
        VALUES (?, ?, 'image/jpeg')
        """,
        (message_id, str(external_image)),
    )
    await test_db.connection.commit()

    result = await test_db.cleanup_old_images(
        retention_days=30,
        orphan_grace_hours=24,
    )

    assert result == {"old_images": 0, "orphan_images": 0, "failed": 0}
    assert external_image.read_bytes() == b"do-not-delete"

    cursor = await test_db.connection.execute(
        "SELECT content FROM messages WHERE id = ?",
        (message_id,),
    )
    assert (await cursor.fetchone())["content"] == "Старый текст"
