# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for usecases cleanup."""

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path

import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.files.image_storage import delete_image
from bot_obormot.services.database.usecases import cleanup as cleanup_usecase
from tests.support.database_repositories import USER_ID as REPOSITORY_USER_ID
from tests.support.database_usecases import USER_ID


async def _insert_message_with_image(
    database: Database,
    user_id: int,
    content: str,
    image_path: Path,
    *,
    age_days: int,
) -> int | None:
    cursor = await database.connection.execute(
        """
        INSERT INTO messages(user_id, role, content, created_at)
        VALUES (?, 'user', ?, datetime('now', ?))
        """,
        (user_id, content, f"-{age_days} days"),
    )
    message_id = cursor.lastrowid
    await database.connection.execute(
        """
        INSERT INTO message_media(message_id, file_path, mime_type)
        VALUES (?, ?, 'image/jpeg')
        """,
        (message_id, str(image_path)),
    )
    await database.connection.commit()
    return message_id


async def _message_content(database: Database, message_id: int | None) -> str:
    cursor = await database.connection.execute(
        "SELECT content FROM messages WHERE id = ?",
        (message_id,),
    )
    row = await cursor.fetchone()
    return str(row["content"])


def _make_expired(path: Path) -> None:
    old_time = time.time() - 48 * 60 * 60
    os.utime(path, (old_time, old_time))


def _write_orphans(images_dir: Path) -> tuple[Path, Path, Path]:
    expired_orphan = images_dir / f"{uuid.uuid4().hex}.jpg"
    recent_orphan = images_dir / f"{uuid.uuid4().hex}.jpg"
    non_managed_file = images_dir / "readme.txt"
    expired_orphan.write_bytes(b"expired")
    recent_orphan.write_bytes(b"recent")
    non_managed_file.write_text("keep this file", encoding="utf-8")
    _make_expired(expired_orphan)
    return expired_orphan, recent_orphan, non_managed_file


def _fail_delete_image(_image_path: Path) -> None:
    msg = "Permission denied"
    raise OSError(msg)


async def _cleanup(
    database: Database,
    delete_image_file: Callable[[Path], None] = delete_image,
) -> dict[str, int]:
    return await cleanup_usecase.cleanup_old_images(
        database.connection,
        database.images_dir,
        retention_days=30,
        orphan_grace_hours=24,
        logger=logging.getLogger(__name__),
        delete_image_file=delete_image_file,
    )


@pytest.mark.asyncio
async def test_cleanup_usecase_counts_the_deleted_old_image(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"old-image")
    await _insert_message_with_image(
        test_db, REPOSITORY_USER_ID, "Старое сообщение", image_path, age_days=60
    )

    result = await test_db.cleanup_old_images(retention_days=30, orphan_grace_hours=24)

    expected_result = {"old_images": 1, "orphan_images": 0, "failed": 0}
    assert result == expected_result, "the cleanup counters differ"


@pytest.mark.asyncio
async def test_cleanup_usecase_deletes_old_image_file(test_db: Database) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"ancient-image")
    await _insert_message_with_image(
        test_db, REPOSITORY_USER_ID, "Давний текст", image_path, age_days=45
    )

    await test_db.cleanup_old_images(retention_days=30, orphan_grace_hours=24)

    assert image_path.exists() is False, "the old image file survived the cleanup"


@pytest.mark.asyncio
async def test_cleanup_usecase_deletes_old_image_but_keeps_message(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"old-image")
    expected_content = "Текст должен сохраниться"
    message_id = await _insert_message_with_image(
        test_db, REPOSITORY_USER_ID, expected_content, image_path, age_days=60
    )

    await test_db.cleanup_old_images(retention_days=30, orphan_grace_hours=24)

    content = await _message_content(test_db, message_id)
    assert content == expected_content, "the message text was changed"


@pytest.mark.asyncio
async def test_cleanup_usecase_counts_only_expired_orphan_images(
    test_db: Database,
) -> None:
    _write_orphans(test_db.images_dir)

    result = await _cleanup(test_db)

    expected_result = {"old_images": 0, "orphan_images": 1, "failed": 0}
    assert result == expected_result, "the cleanup counters differ"


@pytest.mark.asyncio
async def test_cleanup_usecase_removes_expired_orphan_images(
    test_db: Database,
) -> None:
    expired_orphan, _recent, _other = _write_orphans(test_db.images_dir)

    await _cleanup(test_db)

    assert expired_orphan.exists() is False, "the expired orphan survived"


@pytest.mark.asyncio
async def test_cleanup_usecase_keeps_recent_orphan_images(
    test_db: Database,
) -> None:
    _expired, recent_orphan, _other = _write_orphans(test_db.images_dir)

    await _cleanup(test_db)

    assert recent_orphan.exists(), "the recent orphan was deleted"


@pytest.mark.asyncio
async def test_cleanup_usecase_keeps_non_managed_files(test_db: Database) -> None:
    _expired, _recent, non_managed_file = _write_orphans(test_db.images_dir)

    await _cleanup(test_db)

    expected_text = "keep this file"
    actual = non_managed_file.read_text(encoding="utf-8")
    assert actual == expected_text, "the non-managed file was changed"


@pytest.mark.parametrize(
    ("retention_days", "orphan_grace_hours", "expected_name"),
    [(0, 24, "retention_days"), (30, 0, "orphan_grace_hours")],
)
@pytest.mark.asyncio
async def test_cleanup_usecase_rejects_invalid_retention_values(
    test_db: Database,
    retention_days: int,
    orphan_grace_hours: int,
    expected_name: str,
) -> None:
    with pytest.raises(ValueError, match=expected_name) as excinfo:
        await cleanup_usecase.cleanup_old_images(
            test_db.connection,
            test_db.images_dir,
            retention_days=retention_days,
            orphan_grace_hours=orphan_grace_hours,
            logger=logging.getLogger(__name__),
        )

    assert excinfo.type is ValueError, "the invalid option raised another error"


@pytest.mark.asyncio
async def test_cleanup_counts_nothing_for_old_image_outside_managed_directory(
    test_db: Database, tmp_path: Path
) -> None:
    external_image = tmp_path.parent / "external-old-image.jpg"
    external_image.write_bytes(b"do-not-delete")
    await _insert_message_with_image(
        test_db, USER_ID, "Старый текст", external_image, age_days=60
    )

    result = await test_db.cleanup_old_images(retention_days=30, orphan_grace_hours=24)

    expected_result = {"old_images": 0, "orphan_images": 0, "failed": 0}
    assert result == expected_result, "the cleanup counters differ"


@pytest.mark.asyncio
async def test_cleanup_skips_old_image_outside_managed_directory(
    test_db: Database, tmp_path: Path
) -> None:
    external_image = tmp_path.parent / "external-ancient-image.jpg"
    expected_read_bytes = b"do-not-delete"
    external_image.write_bytes(expected_read_bytes)
    await _insert_message_with_image(
        test_db, USER_ID, "Давняя переписка", external_image, age_days=90
    )

    await test_db.cleanup_old_images(retention_days=30, orphan_grace_hours=24)

    actual = external_image.read_bytes()
    assert actual == expected_read_bytes, "the external image was changed"


@pytest.mark.asyncio
async def test_cleanup_keeps_message_of_image_outside_managed_directory(
    test_db: Database, tmp_path: Path
) -> None:
    external_image = tmp_path.parent / "external-old-photo.jpg"
    external_image.write_bytes(b"leave-me")
    expected_content = "Старый текст"
    message_id = await _insert_message_with_image(
        test_db, USER_ID, expected_content, external_image, age_days=60
    )

    await test_db.cleanup_old_images(retention_days=30, orphan_grace_hours=24)

    content = await _message_content(test_db, message_id)
    assert content == expected_content, "the message text was changed"


@pytest.mark.asyncio
async def test_cleanup_counts_nothing_for_recent_referenced_images(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"referenced-image")
    await _insert_message_with_image(
        test_db, USER_ID, "Recent message", image_path, age_days=0
    )

    result = await _cleanup(test_db)

    expected_result = {"old_images": 0, "orphan_images": 0, "failed": 0}
    assert result == expected_result, "the cleanup counters differ"


@pytest.mark.asyncio
async def test_cleanup_keeps_recent_referenced_image_files(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"fresh-referenced-image")
    await _insert_message_with_image(
        test_db, USER_ID, "Fresh message", image_path, age_days=0
    )

    await _cleanup(test_db)

    assert await asyncio.to_thread(image_path.exists), "the recent image was deleted"


@pytest.mark.asyncio
async def test_cleanup_keeps_the_media_row_of_a_recent_image(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"row-referenced-image")
    message_id = await _insert_message_with_image(
        test_db, USER_ID, "Today message", image_path, age_days=0
    )

    await _cleanup(test_db)

    cursor = await test_db.connection.execute(
        "SELECT file_path FROM message_media WHERE message_id = ?",
        (message_id,),
    )
    row = await cursor.fetchone()
    assert row["file_path"] == str(image_path), "the media row was changed"


@pytest.mark.asyncio
async def test_cleanup_reports_old_image_deletion_failure(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"old-image")
    await _insert_message_with_image(
        test_db, USER_ID, "Old message", image_path, age_days=60
    )

    result = await _cleanup(test_db, _fail_delete_image)

    expected_result = {"old_images": 0, "orphan_images": 0, "failed": 1}
    assert result == expected_result, "the failed deletion was not counted"


@pytest.mark.asyncio
async def test_cleanup_leaves_old_image_when_its_deletion_fails(
    test_db: Database,
) -> None:
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"locked-old-image")
    await _insert_message_with_image(
        test_db, USER_ID, "Locked message", image_path, age_days=75
    )

    await _cleanup(test_db, _fail_delete_image)

    assert await asyncio.to_thread(image_path.exists), "the image file vanished"


@pytest.mark.asyncio
async def test_cleanup_reports_images_directory_scan_failure(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def fail_scan(_images_dir: Path) -> list[Path]:
        msg = "Directory scan failed"
        raise OSError(msg)

    monkeypatch.setattr(cleanup_usecase, "list_image_files", fail_scan)

    result = await _cleanup(test_db)

    expected_result = {"old_images": 0, "orphan_images": 0, "failed": 1}
    assert result == expected_result, "the scan failure was not counted"


@pytest.mark.asyncio
async def test_cleanup_reports_orphan_image_deletion_failure(
    test_db: Database,
) -> None:
    orphan_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    orphan_path.write_bytes(b"expired-orphan")
    _make_expired(orphan_path)

    result = await _cleanup(test_db, _fail_delete_image)

    expected_result = {"old_images": 0, "orphan_images": 0, "failed": 1}
    assert result == expected_result, "the failed deletion was not counted"


@pytest.mark.asyncio
async def test_cleanup_leaves_orphan_image_when_its_deletion_fails(
    test_db: Database,
) -> None:
    orphan_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    orphan_path.write_bytes(b"stuck-orphan")
    _make_expired(orphan_path)

    await _cleanup(test_db, _fail_delete_image)

    assert await asyncio.to_thread(orphan_path.exists), "the orphan file vanished"
