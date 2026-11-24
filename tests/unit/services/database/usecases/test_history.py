# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for usecases history."""

import asyncio
import base64
import io
import logging
import uuid
from pathlib import Path

import pytest
from PIL import Image

from bot_obormot.services.database import Database
from bot_obormot.services.database.usecases import history as history_usecase
from tests.support.database_repositories import USER_ID


@pytest.mark.asyncio
async def test_history_usecase_returns_image_parts_and_reset_removes_files(
    test_db: Database,
) -> None:
    await test_db.add_exchange(
        USER_ID,
        "Посмотри на изображение",
        "На изображении объект",
        media=[b"test-image-bytes"],
    )

    history = await test_db.get_history(USER_ID)
    expected_count = 2
    assert len(history) == expected_count
    assert history[0]["content"][0] == {
        "type": "text",
        "text": "Посмотри на изображение",
    }
    image_url = history[0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/jpeg;base64,")

    cursor = await test_db.connection.execute("SELECT file_path FROM message_media")
    image_path = Path((await cursor.fetchone())["file_path"])
    assert await asyncio.to_thread(image_path.exists)

    await test_db.reset_history(USER_ID)
    assert await test_db.get_history(USER_ID) == []
    assert not await asyncio.to_thread(image_path.exists)


@pytest.mark.asyncio
async def test_history_combines_all_legacy_animation_frames_into_one_image(
    test_db: Database,
) -> None:
    frames = []
    for index in range(6):
        output = io.BytesIO()
        Image.new("RGB", (48, 32), (index * 30, 80, 140)).save(
            output,
            format="JPEG",
        )
        frames.append(output.getvalue())

    await test_db.add_exchange(
        USER_ID,
        "Посмотри на стикер",
        "Это анимированный стикер",
        media=frames,
    )

    history = await test_db.get_history(USER_ID, max_images=1)
    user_content = history[0]["content"]

    assert user_content[0] == {
        "type": "text",
        "text": "Посмотри на стикер",
    }
    expected_count = 2
    assert len(user_content) == expected_count

    data_url = user_content[1]["image_url"]["url"]
    image_data = base64.b64decode(data_url.split(",", 1)[1])
    with Image.open(io.BytesIO(image_data)) as contact_sheet:
        expected_format = "JPEG"
        assert contact_sheet.format == expected_format
        assert contact_sheet.size == (3 * 512, 2 * 384)


@pytest.mark.asyncio
async def test_reset_history_does_not_delete_unmanaged_or_external_files(
    test_db: Database, tmp_path: Path
) -> None:
    managed_image = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    unmanaged_image = test_db.images_dir / "notes.txt"
    external_image = tmp_path / f"{uuid.uuid4().hex}.jpg"
    for path in (managed_image, unmanaged_image, external_image):
        path.write_bytes(b"keep-or-delete-check")

    cursor = await test_db.connection.execute(
        "INSERT INTO messages(user_id, role, content) VALUES (?, 'user', 'clear me')",
        (USER_ID,),
    )
    message_id = cursor.lastrowid
    for path in (managed_image, unmanaged_image, external_image):
        await test_db.connection.execute(
            "INSERT INTO message_media(message_id, file_path, mime_type) "
            "VALUES (?, ?, 'image/jpeg')",
            (message_id, str(path)),
        )
    await test_db.connection.commit()

    await test_db.reset_history(USER_ID)

    assert not managed_image.exists()
    expected_read_bytes = b"keep-or-delete-check"
    assert unmanaged_image.read_bytes() == expected_read_bytes
    expected_read_bytes = b"keep-or-delete-check"
    assert external_image.read_bytes() == expected_read_bytes
    assert await test_db.get_history(USER_ID) == []


@pytest.mark.asyncio
async def test_history_keeps_image_parts_when_contact_sheet_creation_fails(
    test_db: Database,
) -> None:
    await test_db.add_exchange(
        USER_ID,
        "Question",
        "Answer",
        media=[b"frame-one", b"frame-two"],
    )

    def read_invalid_image(_image_path: Path, _mime_type: str) -> str:
        return "invalid-data-url"

    history = await history_usecase.get_history(
        test_db.connection,
        USER_ID,
        limit=10,
        max_images=1,
        read_image_as_base64=read_invalid_image,
        logger=logging.getLogger(__name__),
    )

    assert history[0]["content"] == [
        {"type": "text", "text": "Question"},
        {
            "type": "image_url",
            "image_url": {"url": "invalid-data-url"},
        },
        {
            "type": "image_url",
            "image_url": {"url": "invalid-data-url"},
        },
    ]


@pytest.mark.parametrize(
    ("error_type", "expected_message"),
    [
        (FileNotFoundError, "History image not found"),
        (PermissionError, "Could not read history image"),
    ],
)
@pytest.mark.asyncio
async def test_history_skips_images_when_image_read_fails(
    test_db: Database,
    caplog: pytest.LogCaptureFixture,
    error_type: type[OSError],
    expected_message: str,
) -> None:
    await test_db.add_exchange(
        USER_ID,
        "Question",
        "Answer",
        media=[b"image-bytes"],
    )

    def fail_read_image(_image_path: Path, _mime_type: str) -> str:
        msg = "Image read failed"
        raise error_type(msg)

    with caplog.at_level(logging.WARNING):
        history = await history_usecase.get_history(
            test_db.connection,
            USER_ID,
            limit=10,
            max_images=1,
            read_image_as_base64=fail_read_image,
            logger=logging.getLogger(__name__),
        )

    expected_content = "Question"
    assert history[0]["content"] == expected_content
    assert expected_message in caplog.text


@pytest.mark.asyncio
async def test_reset_history_keeps_database_reset_when_image_delete_fails(
    test_db: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await test_db.add_exchange(
        USER_ID,
        "Question",
        "Answer",
        media=[b"image-bytes"],
    )

    cursor = await test_db.connection.execute("SELECT file_path FROM message_media")
    image_path = Path((await cursor.fetchone())["file_path"])

    def fail_delete_image(_image_path: Path) -> None:
        msg = "Permission denied"
        raise OSError(msg)

    with caplog.at_level(logging.ERROR):
        await history_usecase.reset_history(
            test_db.connection,
            USER_ID,
            fail_delete_image,
            logging.getLogger(__name__),
            images_dir=test_db.images_dir,
        )

    assert await test_db.get_history(USER_ID) == []
    assert await asyncio.to_thread(image_path.exists)
    cleanup_warning = "Could not remove image during history reset"
    assert cleanup_warning in caplog.text
