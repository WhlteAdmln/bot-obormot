# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for usecases history."""

import asyncio
import base64
import io
import logging
import uuid
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from bot_obormot.services.database import Database
from bot_obormot.services.database.usecases import history as history_usecase
from tests.support.database_repositories import USER_ID


async def _first_image_path(database: Database) -> Path:
    cursor = await database.connection.execute("SELECT file_path FROM message_media")
    row = await cursor.fetchone()
    return Path(row["file_path"])


def _jpeg_frames(count: int) -> list[bytes]:
    frames = []
    for index in range(count):
        output = io.BytesIO()
        Image.new("RGB", (48, 32), (index * 30, 80, 140)).save(output, format="JPEG")
        frames.append(output.getvalue())
    return frames


async def _contact_sheet_content(
    database: Database, prompt: str
) -> list[dict[str, Any]]:
    await database.add_exchange(
        USER_ID,
        prompt,
        "Это анимированный стикер",
        media=_jpeg_frames(6),
    )
    history = await database.get_history(USER_ID, max_images=1)
    content: list[dict[str, Any]] = history[0]["content"]
    return content


def _decoded_image(data_url: str) -> Image.Image:
    image_data = base64.b64decode(data_url.split(",", 1)[1])
    with Image.open(io.BytesIO(image_data)) as image:
        image.load()
        return image


async def _store_media_rows(database: Database, paths: list[Path]) -> None:
    for path in paths:
        path.write_bytes(b"keep-or-delete-check")
    cursor = await database.connection.execute(
        "INSERT INTO messages(user_id, role, content) VALUES (?, 'user', 'clear me')",
        (USER_ID,),
    )
    message_id = cursor.lastrowid
    for path in paths:
        await database.connection.execute(
            "INSERT INTO message_media(message_id, file_path, mime_type) "
            "VALUES (?, ?, 'image/jpeg')",
            (message_id, str(path)),
        )
    await database.connection.commit()


def _fail_delete_image(_image_path: Path) -> None:
    msg = "Permission denied"
    raise OSError(msg)


async def _reset_with_failing_delete(database: Database) -> None:
    await history_usecase.reset_history(
        database.connection,
        USER_ID,
        _fail_delete_image,
        logging.getLogger(__name__),
        images_dir=database.images_dir,
    )


@pytest.mark.asyncio
async def test_history_returns_the_user_and_assistant_messages(
    test_db: Database,
) -> None:
    await test_db.add_exchange(
        USER_ID, "Что на картинке?", "Кот", media=[b"test-image-bytes"]
    )

    history = await test_db.get_history(USER_ID)

    expected_count = 2
    assert len(history) == expected_count, "the exchange was not stored as two rows"


@pytest.mark.asyncio
async def test_history_starts_the_user_content_with_its_text(
    test_db: Database,
) -> None:
    prompt = "Посмотри на изображение"
    await test_db.add_exchange(
        USER_ID, prompt, "На изображении объект", media=[b"test-image-bytes"]
    )

    history = await test_db.get_history(USER_ID)

    expected_part = {"type": "text", "text": prompt}
    assert history[0]["content"][0] == expected_part, "the text part differs"


@pytest.mark.asyncio
async def test_history_returns_the_image_as_a_jpeg_data_url(
    test_db: Database,
) -> None:
    await test_db.add_exchange(
        USER_ID, "Опиши фото", "Пейзаж", media=[b"another-image-bytes"]
    )

    history = await test_db.get_history(USER_ID)

    image_url = history[0]["content"][1]["image_url"]["url"]
    prefix = "data:image/jpeg;base64,"
    assert image_url.startswith(prefix), "the image is not a JPEG data URL"


@pytest.mark.asyncio
async def test_add_exchange_stores_the_image_file(test_db: Database) -> None:
    await test_db.add_exchange(
        USER_ID, "Сохрани снимок", "Сохранил", media=[b"stored-image-bytes"]
    )

    image_path = await _first_image_path(test_db)

    assert await asyncio.to_thread(image_path.exists), "the image file is missing"


@pytest.mark.asyncio
async def test_reset_history_empties_the_history(test_db: Database) -> None:
    await test_db.add_exchange(
        USER_ID, "Забудь это фото", "Хорошо", media=[b"forget-image-bytes"]
    )

    await test_db.reset_history(USER_ID)

    expected_empty: list[dict[str, Any]] = []
    history = await test_db.get_history(USER_ID)
    assert history == expected_empty, "the history survived the reset"


@pytest.mark.asyncio
async def test_reset_history_removes_the_image_file(test_db: Database) -> None:
    await test_db.add_exchange(
        USER_ID, "Удали снимок", "Удалю", media=[b"removed-image-bytes"]
    )
    image_path = await _first_image_path(test_db)

    await test_db.reset_history(USER_ID)

    exists = await asyncio.to_thread(image_path.exists)
    assert exists is False, "the image file survived the reset"


@pytest.mark.asyncio
async def test_history_keeps_the_text_part_of_legacy_animation_frames(
    test_db: Database,
) -> None:
    prompt = "Посмотри на стикер"

    user_content = await _contact_sheet_content(test_db, prompt)

    expected_part = {"type": "text", "text": prompt}
    assert user_content[0] == expected_part, "the text part differs"


@pytest.mark.asyncio
async def test_history_combines_all_legacy_animation_frames_into_one_image(
    test_db: Database,
) -> None:
    user_content = await _contact_sheet_content(test_db, "Что за анимация?")

    expected_count = 2
    assert len(user_content) == expected_count, "the frames were not combined"


@pytest.mark.asyncio
async def test_history_encodes_the_contact_sheet_as_jpeg(test_db: Database) -> None:
    user_content = await _contact_sheet_content(test_db, "Глянь на гифку")

    contact_sheet = _decoded_image(user_content[1]["image_url"]["url"])

    expected_format = "JPEG"
    assert contact_sheet.format == expected_format, "the contact sheet is not a JPEG"


@pytest.mark.asyncio
async def test_history_lays_six_frames_out_in_a_three_by_two_sheet(
    test_db: Database,
) -> None:
    user_content = await _contact_sheet_content(test_db, "Покажи все кадры")

    contact_sheet = _decoded_image(user_content[1]["image_url"]["url"])

    expected_size = (3 * 512, 2 * 384)
    assert contact_sheet.size == expected_size, "the contact sheet size differs"


@pytest.mark.asyncio
async def test_reset_history_deletes_the_managed_image(test_db: Database) -> None:
    managed_image = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    await _store_media_rows(test_db, [managed_image])

    await test_db.reset_history(USER_ID)

    assert managed_image.exists() is False, "the managed image survived the reset"


@pytest.mark.asyncio
async def test_reset_history_does_not_delete_unmanaged_files(
    test_db: Database,
) -> None:
    unmanaged_image = test_db.images_dir / "notes.txt"
    await _store_media_rows(test_db, [unmanaged_image])

    await test_db.reset_history(USER_ID)

    expected_read_bytes = b"keep-or-delete-check"
    actual = unmanaged_image.read_bytes()
    assert actual == expected_read_bytes, "the unmanaged file was changed"


@pytest.mark.asyncio
async def test_reset_history_does_not_delete_external_files(
    test_db: Database, tmp_path: Path
) -> None:
    external_image = tmp_path / f"{uuid.uuid4().hex}.jpg"
    await _store_media_rows(test_db, [external_image])

    await test_db.reset_history(USER_ID)

    expected_read_bytes = b"keep-or-delete-check"
    actual = external_image.read_bytes()
    assert actual == expected_read_bytes, "the external file was changed"


@pytest.mark.asyncio
async def test_reset_history_with_mixed_media_empties_the_history(
    test_db: Database, tmp_path: Path
) -> None:
    paths = [
        test_db.images_dir / f"{uuid.uuid4().hex}.jpg",
        test_db.images_dir / "notes.txt",
        tmp_path / f"{uuid.uuid4().hex}.jpg",
    ]
    await _store_media_rows(test_db, paths)

    await test_db.reset_history(USER_ID)

    expected_empty: list[dict[str, Any]] = []
    history = await test_db.get_history(USER_ID)
    assert history == expected_empty, "the history survived the reset"


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

    expected_content = [
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
    assert history[0]["content"] == expected_content, "the image parts were lost"


@pytest.mark.parametrize("error_type", [FileNotFoundError, PermissionError])
@pytest.mark.asyncio
async def test_history_skips_images_when_image_read_fails(
    test_db: Database,
    error_type: type[OSError],
) -> None:
    prompt = "Unreadable picture question"
    await test_db.add_exchange(USER_ID, prompt, "Answer", media=[b"image-bytes"])

    def fail_read_image(_image_path: Path, _mime_type: str) -> str:
        msg = "Image read failed"
        raise error_type(msg)

    history = await history_usecase.get_history(
        test_db.connection,
        USER_ID,
        limit=10,
        max_images=1,
        read_image_as_base64=fail_read_image,
        logger=logging.getLogger(__name__),
    )

    assert history[0]["content"] == prompt, "the unreadable image was kept"


@pytest.mark.parametrize(
    ("error_type", "expected_message"),
    [
        (FileNotFoundError, "History image not found"),
        (PermissionError, "Could not read history image"),
    ],
)
@pytest.mark.asyncio
async def test_history_logs_a_warning_when_image_read_fails(
    test_db: Database,
    caplog: pytest.LogCaptureFixture,
    error_type: type[OSError],
    expected_message: str,
) -> None:
    await test_db.add_exchange(
        USER_ID, "Broken picture", "Reply", media=[b"broken-image-bytes"]
    )

    def fail_read_image(_image_path: Path, _mime_type: str) -> str:
        msg = "Image read failed"
        raise error_type(msg)

    with caplog.at_level(logging.WARNING):
        await history_usecase.get_history(
            test_db.connection,
            USER_ID,
            limit=10,
            max_images=1,
            read_image_as_base64=fail_read_image,
            logger=logging.getLogger(__name__),
        )

    assert expected_message in caplog.text, "the read failure was not logged"


@pytest.mark.asyncio
async def test_reset_history_keeps_database_reset_when_image_delete_fails(
    test_db: Database,
) -> None:
    await test_db.add_exchange(USER_ID, "Question", "Answer", media=[b"image-bytes"])

    await _reset_with_failing_delete(test_db)

    expected_empty: list[dict[str, Any]] = []
    history = await test_db.get_history(USER_ID)
    assert history == expected_empty, "the history survived the reset"


@pytest.mark.asyncio
async def test_reset_history_leaves_the_image_when_its_delete_fails(
    test_db: Database,
) -> None:
    await test_db.add_exchange(
        USER_ID, "Stubborn file", "Noted", media=[b"stubborn-image-bytes"]
    )
    image_path = await _first_image_path(test_db)

    await _reset_with_failing_delete(test_db)

    assert await asyncio.to_thread(image_path.exists), "the image file vanished"


@pytest.mark.asyncio
async def test_reset_history_logs_the_image_delete_failure(
    test_db: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await test_db.add_exchange(
        USER_ID, "Locked file", "Fine", media=[b"locked-image-bytes"]
    )

    with caplog.at_level(logging.ERROR):
        await _reset_with_failing_delete(test_db)

    cleanup_warning = "Could not remove image during history reset"
    assert cleanup_warning in caplog.text, "the delete failure was not logged"
