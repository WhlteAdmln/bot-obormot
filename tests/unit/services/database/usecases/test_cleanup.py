# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for usecases cleanup."""

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.usecases import cleanup as cleanup_usecase
from tests.support.database_repositories import USER_ID as REPOSITORY_USER_ID
from tests.support.database_usecases import USER_ID


@pytest.mark.asyncio
async def test_cleanup_usecase_deletes_old_image_but_keeps_message(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"old-image")

    cursor = await test_db.connection.execute(
        """
        INSERT INTO messages(user_id, role, content, created_at)
        VALUES (?, 'user', 'Текст должен сохраниться', datetime('now', '-60 days'))
        """,
        (REPOSITORY_USER_ID,),
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

    result = await test_db.cleanup_old_images(
        retention_days=30,
        orphan_grace_hours=24,
    )

    assert result == {
        "old_images": 1,
        "orphan_images": 0,
        "failed": 0,
    }
    assert not image_path.exists()

    cursor = await test_db.connection.execute(
        "SELECT content FROM messages WHERE id = ?",
        (message_id,),
    )
    expected_content = "Текст должен сохраниться"
    assert (await cursor.fetchone())["content"] == expected_content


@pytest.mark.asyncio
async def test_cleanup_usecase_removes_only_expired_orphan_images(
    test_db: Database,
) -> None:
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
    expected_text = "keep this file"
    assert non_managed_file.read_text(encoding="utf-8") == expected_text


@pytest.mark.asyncio
async def test_cleanup_usecase_rejects_invalid_retention_values(
    test_db: Database,
) -> None:
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
    expected_read_bytes = b"do-not-delete"
    assert external_image.read_bytes() == expected_read_bytes

    cursor = await test_db.connection.execute(
        "SELECT content FROM messages WHERE id = ?",
        (message_id,),
    )
    expected_content = "Старый текст"
    assert (await cursor.fetchone())["content"] == expected_content


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_referenced_image_files(
    test_db: Database,
) -> None:
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
