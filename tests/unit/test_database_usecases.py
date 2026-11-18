# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database usecases."""

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

import aiosqlite
import pytest

from bot_obormot.errors import DatabaseError, MediaError
from bot_obormot.services.database import Database
from bot_obormot.services.database.usecases import cleanup as cleanup_usecase
from bot_obormot.services.database.usecases import exchange as exchange_usecase

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


@pytest.mark.asyncio
async def test_add_exchange_does_not_rollback_transaction_it_did_not_start(
    test_db: Database,
) -> None:
    """Add exchange preserves a transaction that it did not start."""
    await test_db.connection.execute("BEGIN")

    with pytest.raises(DatabaseError, match="Could not save message exchange"):
        await test_db.add_exchange(
            USER_ID,
            "Вопрос",
            "Ответ",
        )

    assert test_db.connection.in_transaction
    await test_db.connection.rollback()
    assert await test_db.get_history(USER_ID) == []


@pytest.mark.asyncio
async def test_add_exchange_handles_rollback_failure(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Add exchange preserves the original error when rollback fails."""
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

    original_rollback = test_db.connection.rollback

    async def fail_rollback() -> None:
        msg = "rollback failed"
        raise aiosqlite.OperationalError(msg)

    with monkeypatch.context() as patcher:
        patcher.setattr(test_db.connection, "rollback", fail_rollback)

        with pytest.raises(
            DatabaseError,
            match="Could not save message exchange",
        ):
            await test_db.add_exchange(
                USER_ID,
                "Вопрос",
                "Ответ",
            )

    await original_rollback()
    assert not test_db.connection.in_transaction
    assert await test_db.get_history(USER_ID) == []


@pytest.mark.asyncio
async def test_add_exchange_reports_image_save_and_cleanup_failures(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Add exchange reports image save failure despite cleanup failure."""

    def fail_save_image(_image_path: Path, _image_data: bytes) -> None:
        msg = "disk full"
        raise OSError(msg)

    def fail_delete_image(_image_path: Path) -> None:
        msg = "permission denied"
        raise OSError(msg)

    monkeypatch.setattr(exchange_usecase, "save_image", fail_save_image)
    monkeypatch.setattr(exchange_usecase, "delete_image", fail_delete_image)

    with pytest.raises(
        MediaError,
        match="Could not save or remove media file",
    ):
        await test_db.add_exchange(
            USER_ID,
            "Вопрос",
            "Ответ",
            media=[b"image-bytes"],
        )

    assert not test_db.connection.in_transaction
    assert await test_db.get_history(USER_ID) == []
    assert list(test_db.images_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_referenced_image_files(
    test_db: Database,
) -> None:
    """Cleanup keeps recent images that are still referenced by messages."""
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"referenced-image")

    cursor = await test_db.connection.execute(
        """
        INSERT INTO messages(user_id, role, content)
        VALUES (?, 'user', 'Recent message')
        """,
        (USER_ID,),
    )
    message_id = cursor.lastrowid
    await test_db.connection.execute(
        """
        INSERT INTO message_media(message_id, file_path, mime_type)
        VALUES (?, ?, 'image/jpeg')
        """,
        (message_id, str(image_path)),
    )
    await test_db.connection.commit()

    result = await cleanup_usecase.cleanup_old_images(
        test_db.connection,
        test_db.images_dir,
        retention_days=30,
        orphan_grace_hours=24,
        logger=logging.getLogger(__name__),
    )

    assert result == {"old_images": 0, "orphan_images": 0, "failed": 0}
    assert await asyncio.to_thread(image_path.exists)

    cursor = await test_db.connection.execute(
        "SELECT file_path FROM message_media WHERE message_id = ?",
        (message_id,),
    )
    assert (await cursor.fetchone())["file_path"] == str(image_path)


@pytest.mark.asyncio
async def test_cleanup_reports_old_image_deletion_failure(
    test_db: Database,
) -> None:
    """Cleanup reports an error when an expired image cannot be deleted."""
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"old-image")

    cursor = await test_db.connection.execute(
        """
        INSERT INTO messages(user_id, role, content, created_at)
        VALUES (?, 'user', 'Old message', datetime('now', '-60 days'))
        """,
        (USER_ID,),
    )
    message_id = cursor.lastrowid
    await test_db.connection.execute(
        """
        INSERT INTO message_media(message_id, file_path, mime_type)
        VALUES (?, ?, 'image/jpeg')
        """,
        (message_id, str(image_path)),
    )
    await test_db.connection.commit()

    def fail_delete_image(_image_path: Path) -> None:
        msg = "Permission denied"
        raise OSError(msg)

    result = await cleanup_usecase.cleanup_old_images(
        test_db.connection,
        test_db.images_dir,
        retention_days=30,
        orphan_grace_hours=24,
        logger=logging.getLogger(__name__),
        delete_image_file=fail_delete_image,
    )

    assert result == {"old_images": 0, "orphan_images": 0, "failed": 1}
    assert await asyncio.to_thread(image_path.exists)


@pytest.mark.asyncio
async def test_cleanup_reports_images_directory_scan_failure(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cleanup reports an error when the images directory cannot be scanned."""

    def fail_scan(_images_dir: Path) -> list[Path]:
        msg = "Directory scan failed"
        raise OSError(msg)

    monkeypatch.setattr(cleanup_usecase, "list_image_files", fail_scan)

    result = await cleanup_usecase.cleanup_old_images(
        test_db.connection,
        test_db.images_dir,
        retention_days=30,
        orphan_grace_hours=24,
        logger=logging.getLogger(__name__),
    )

    assert result == {"old_images": 0, "orphan_images": 0, "failed": 1}


@pytest.mark.asyncio
async def test_cleanup_reports_orphan_image_deletion_failure(
    test_db: Database,
) -> None:
    """Cleanup reports an error when an expired orphan cannot be deleted."""
    orphan_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    orphan_path.write_bytes(b"expired-orphan")
    old_time = time.time() - 48 * 60 * 60
    os.utime(orphan_path, (old_time, old_time))

    def fail_delete_image(_image_path: Path) -> None:
        msg = "Permission denied"
        raise OSError(msg)

    result = await cleanup_usecase.cleanup_old_images(
        test_db.connection,
        test_db.images_dir,
        retention_days=30,
        orphan_grace_hours=24,
        logger=logging.getLogger(__name__),
        delete_image_file=fail_delete_image,
    )

    assert result == {"old_images": 0, "orphan_images": 0, "failed": 1}
    assert await asyncio.to_thread(orphan_path.exists)
