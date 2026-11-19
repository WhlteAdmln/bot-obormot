# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database repositories."""

import asyncio
import base64
import io
import logging
import uuid
from pathlib import Path

import pytest
from PIL import Image

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    admins,
    history_limits,
    media,
    messages,
    user_settings,
)
from bot_obormot.services.database.usecases import history as history_usecase

USER_ID = 515151


@pytest.mark.asyncio
async def test_messages_repository_adds_and_fetches_complete_exchanges(
    test_db: Database,
) -> None:
    """Messages repository adds and fetches complete exchanges."""
    await messages.add_message(test_db.connection, USER_ID, "user", "Вопрос")
    await messages.add_message(test_db.connection, USER_ID, "assistant", "Ответ")
    await messages.add_message(test_db.connection, USER_ID, "user", "Без ответа")

    rows = await messages.fetch_history_rows(
        test_db.connection,
        USER_ID,
        exchange_limit=10,
        max_images=3,
    )

    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "Вопрос"),
        ("assistant", "Ответ"),
    ]


@pytest.mark.asyncio
async def test_user_settings_repository_crud(test_db: Database) -> None:
    """User settings repository crud."""
    assert await user_settings.get_system_prompt(test_db.connection, USER_ID) is None

    await user_settings.set_system_prompt(
        test_db.connection,
        USER_ID,
        "Персональный промпт",
    )
    assert (
        await user_settings.get_system_prompt(test_db.connection, USER_ID)
        == "Персональный промпт"
    )

    await user_settings.delete_system_prompt(test_db.connection, USER_ID)
    assert await user_settings.get_system_prompt(test_db.connection, USER_ID) is None


@pytest.mark.asyncio
async def test_history_limits_repository_crud(test_db: Database) -> None:
    """History limits repository crud."""
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) is None

    await history_limits.set_history_limit(test_db.connection, USER_ID, 17)
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) == 17

    await history_limits.delete_history_limit(test_db.connection, USER_ID)
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) is None


@pytest.mark.asyncio
async def test_admins_repository_is_idempotent_and_facade_excludes_supervisor(
    test_db: Database,
) -> None:
    """Admins repository is idempotent and facade excludes supervisor."""
    assert await admins.add_admin(test_db.connection, USER_ID) is True
    assert await admins.add_admin(test_db.connection, USER_ID) is False
    assert await test_db.get_admin_ids() == {USER_ID}

    assert await test_db.add_admin(test_db.settings.SUPERVISOR_ID) is False
    assert await test_db.remove_admin(test_db.settings.SUPERVISOR_ID) is False
    assert await test_db.get_admin_ids() == {USER_ID}

    assert await admins.remove_admin(test_db.connection, USER_ID) is True
    assert await admins.remove_admin(test_db.connection, USER_ID) is False


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
    assert (await cursor.fetchone())["content"] == "Старое сообщение"


@pytest.mark.asyncio
async def test_history_usecase_returns_image_parts_and_reset_removes_files(
    test_db: Database,
) -> None:
    """History usecase returns image parts and reset removes files."""
    await test_db.add_exchange(
        USER_ID,
        "Посмотри на изображение",
        "На изображении объект",
        media=[b"test-image-bytes"],
    )

    history = await test_db.get_history(USER_ID)
    assert len(history) == 2
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
    """History combines all legacy animation frames into one image."""
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

    # max_images теперь ограничивает число медиа-сообщений, а не кадров
    # внутри одного сообщения: все шесть исторических кадров загружаются.
    history = await test_db.get_history(USER_ID, max_images=1)
    user_content = history[0]["content"]

    assert user_content[0] == {
        "type": "text",
        "text": "Посмотри на стикер",
    }
    assert len(user_content) == 2

    data_url = user_content[1]["image_url"]["url"]
    image_data = base64.b64decode(data_url.split(",", 1)[1])
    with Image.open(io.BytesIO(image_data)) as contact_sheet:
        assert contact_sheet.format == "JPEG"
        assert contact_sheet.size == (3 * 512, 2 * 384)


@pytest.mark.asyncio
async def test_reset_history_does_not_delete_unmanaged_or_external_files(
    test_db: Database, tmp_path: Path
) -> None:
    """Reset history does not delete unmanaged or external files."""
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
    assert unmanaged_image.read_bytes() == b"keep-or-delete-check"
    assert external_image.read_bytes() == b"keep-or-delete-check"
    assert await test_db.get_history(USER_ID) == []


@pytest.mark.asyncio
async def test_facade_system_prompt_methods_preserve_default_behavior(
    test_db: Database,
) -> None:
    """Facade system prompt methods preserve default behavior."""
    assert (
        await test_db.get_system_prompt(USER_ID)
        == test_db.settings.DEFAULT_SYSTEM_PROMPT
    )
    await test_db.set_system_prompt(USER_ID, "Новый промпт")
    assert await test_db.get_user_system_prompt(USER_ID) == "Новый промпт"


@pytest.mark.asyncio
async def test_cleanup_usecase_deletes_old_image_but_keeps_message(
    test_db: Database,
) -> None:
    """Cleanup usecase deletes old image but keeps message."""
    image_path = test_db.images_dir / f"{uuid.uuid4().hex}.jpg"
    image_path.write_bytes(b"old-image")

    cursor = await test_db.connection.execute(
        """
        INSERT INTO messages(user_id, role, content, created_at)
        VALUES (?, 'user', 'Текст должен сохраниться', datetime('now', '-60 days'))
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
    assert (await cursor.fetchone())["content"] == "Текст должен сохраниться"


@pytest.mark.asyncio
async def test_history_keeps_image_parts_when_contact_sheet_creation_fails(
    test_db: Database,
) -> None:
    """History keeps original image parts when contact sheet creation fails."""
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
    """History skips an image when reading it fails."""
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

    assert history[0]["content"] == "Question"
    assert expected_message in caplog.text


@pytest.mark.asyncio
async def test_reset_history_keeps_database_reset_when_image_delete_fails(
    test_db: Database,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reset history removes messages even when image deletion fails."""
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
    assert "Could not remove image during history reset" in caplog.text
