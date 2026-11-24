# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the history operations of the database facade."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from bot_obormot.errors import DatabaseError
from bot_obormot.services.database import Database

USER_ID = 111111111

USER_A = 111111111


@pytest.mark.asyncio
async def test_history_limit_counts_complete_exchanges(test_db: Database) -> None:
    """History limit counts complete exchanges."""
    for number in range(5):
        await test_db.add_exchange(
            USER_ID,
            f"Вопрос {number}",
            f"Ответ {number}",
        )

    history = await test_db.get_history(USER_ID, limit=2)

    expected_count = 4
    assert len(history) == expected_count

    assert [item["content"] for item in history] == [
        "Вопрос 3",
        "Ответ 3",
        "Вопрос 4",
        "Ответ 4",
    ]


@pytest.mark.asyncio
async def test_history_limit_zero_returns_empty_history(test_db: Database) -> None:
    """History limit zero returns empty history."""
    await test_db.add_exchange(
        USER_ID,
        "Вопрос",
        "Ответ",
    )

    assert await test_db.get_history(USER_ID, limit=0) == []


@pytest.mark.asyncio
async def test_history_ignores_incomplete_messages(test_db: Database) -> None:
    """History ignores incomplete messages."""
    await test_db.add_exchange(
        USER_ID,
        "Вопрос 1",
        "Ответ 1",
    )

    await test_db.add_message(
        USER_ID,
        "user",
        "Незавершённый вопрос",
    )

    history = await test_db.get_history(USER_ID, limit=10)

    expected_count = 2
    assert len(history) == expected_count

    assert [item["content"] for item in history] == [
        "Вопрос 1",
        "Ответ 1",
    ]


@pytest.mark.asyncio
async def test_history_limit_isolated_between_users(test_db: Database) -> None:
    """History limit isolated between users."""
    await test_db.set_history_limit(USER_ID, 10)
    await test_db.set_history_limit(USER_ID + 1, 5)

    expected_number = 10
    assert await test_db.get_history_limit(USER_ID) == expected_number
    expected_number = 5
    assert await test_db.get_history_limit(USER_ID + 1) == expected_number

    assert (
        await test_db.get_history_limit(USER_ID + 2)
        == test_db.settings.DEFAULT_HISTORY_EXCHANGES
    )


@pytest.mark.asyncio
async def test_prune_history_keeps_latest_exchanges_and_removes_old_images(
    test_db: Database,
    tmp_path: Path,
) -> None:
    """Prune history keeps latest exchanges and removes old images."""
    test_db.settings = replace(test_db.settings, MAX_STORED_EXCHANGES=2)
    old_image_path = None
    latest_image_path = None
    external_image_path = tmp_path / "external-old-image.jpg"
    external_image_path.write_bytes(b"must not be deleted")

    for number in range(5):
        media = [f"image-{number}".encode()] if number in {0, 4} else None
        await test_db.add_exchange(
            USER_ID,
            f"Вопрос {number}",
            f"Ответ {number}",
            media=media,
        )
        expected_number = 4
        if number == 0:
            cursor = await test_db.connection.execute(
                "SELECT file_path FROM message_media ORDER BY id DESC LIMIT 1"
            )
            old_image_path = Path((await cursor.fetchone())["file_path"])
            cursor = await test_db.connection.execute(
                "SELECT id FROM messages WHERE user_id = ? AND content = ?",
                (USER_ID, "Вопрос 0"),
            )
            old_message_id = (await cursor.fetchone())["id"]
            await test_db.connection.execute(
                "INSERT INTO message_media(message_id, file_path, mime_type) "
                "VALUES (?, ?, 'image/jpeg')",
                (old_message_id, str(external_image_path)),
            )
            await test_db.connection.commit()
        elif number == expected_number:
            cursor = await test_db.connection.execute(
                "SELECT file_path FROM message_media ORDER BY id DESC LIMIT 1"
            )
            latest_image_path = Path((await cursor.fetchone())["file_path"])

    # История другого пользователя не должна затрагиваться.
    other_user_id = USER_ID + 1
    for number in range(5):
        await test_db.add_exchange(
            other_user_id,
            f"Другой вопрос {number}",
            f"Другой ответ {number}",
        )

    await test_db.prune_history(USER_ID)

    cursor = await test_db.connection.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id",
        (USER_ID,),
    )
    rows = await cursor.fetchall()
    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "Вопрос 3"),
        ("assistant", "Ответ 3"),
        ("user", "Вопрос 4"),
        ("assistant", "Ответ 4"),
    ]

    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM messages WHERE user_id = ?",
        (other_user_id,),
    )
    expected_total = 10
    assert (await cursor.fetchone())["total"] == expected_total
    assert old_image_path is not None
    assert not old_image_path.exists()
    assert latest_image_path is not None
    assert latest_image_path.exists()
    expected_read_bytes = b"must not be deleted"
    assert external_image_path.read_bytes() == expected_read_bytes

    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM message_media mm "
        "JOIN messages m ON m.id = mm.message_id WHERE m.user_id = ?",
        (USER_ID,),
    )
    assert (await cursor.fetchone())["total"] == 1


@pytest.mark.asyncio
async def test_forget_user_removes_history_prompt_limit_and_owned_images(
    test_db: Database,
) -> None:
    """Forget user removes history prompt limit and owned images."""
    user_id = USER_ID + 20
    other_user_id = USER_ID + 21

    await test_db.set_system_prompt(user_id, "Персональный промпт")
    await test_db.set_history_limit(user_id, 17)
    await test_db.add_exchange(
        user_id,
        "Мой вопрос",
        "Мой ответ",
        media=[b"my-image"],
    )

    await test_db.set_system_prompt(other_user_id, "Чужой промпт")
    await test_db.set_history_limit(other_user_id, 23)
    await test_db.add_exchange(
        other_user_id,
        "Чужой вопрос",
        "Чужой ответ",
        media=[b"other-image"],
    )

    cursor = await test_db.connection.execute(
        "SELECT mm.file_path FROM message_media mm "
        "JOIN messages m ON m.id = mm.message_id WHERE m.user_id = ?",
        (user_id,),
    )
    own_image_path = Path((await cursor.fetchone())["file_path"])
    cursor = await test_db.connection.execute(
        "SELECT mm.file_path FROM message_media mm "
        "JOIN messages m ON m.id = mm.message_id WHERE m.user_id = ?",
        (other_user_id,),
    )
    other_image_path = Path((await cursor.fetchone())["file_path"])

    assert await asyncio.to_thread(own_image_path.exists)
    assert await asyncio.to_thread(other_image_path.exists)

    await test_db.forget_user(user_id)

    assert await test_db.get_user_system_prompt(user_id) is None
    assert (
        await test_db.get_system_prompt(user_id)
        == test_db.settings.DEFAULT_SYSTEM_PROMPT
    )
    assert (
        await test_db.get_history_limit(user_id)
        == test_db.settings.DEFAULT_HISTORY_EXCHANGES
    )
    assert await test_db.get_history(user_id) == []
    assert not await asyncio.to_thread(own_image_path.exists)

    # Команда одного пользователя не затрагивает данные другого.
    expected_text = "Чужой промпт"
    assert await test_db.get_user_system_prompt(other_user_id) == expected_text
    expected_number = 23
    assert await test_db.get_history_limit(other_user_id) == expected_number
    other_history = await test_db.get_history(other_user_id)
    expected_text = "Чужой вопрос"
    assert other_history[0]["content"][0]["text"] == expected_text
    expected_type = "image_url"
    assert other_history[0]["content"][1]["type"] == expected_type
    expected_content = "Чужой ответ"
    assert other_history[1]["content"] == expected_content
    assert await asyncio.to_thread(other_image_path.exists)


@pytest.mark.asyncio
async def test_failed_exchange_rollback(test_db: Database) -> None:
    """Проверяет откат неудачного обмена и удаление изображения."""
    db = test_db

    image_data = b"fake-image-data"

    with pytest.raises(DatabaseError):
        await db.add_exchange(
            USER_A,
            "Тестовое сообщение",
            None,
            media=[image_data],
        )

    # Неудачный обмен не должен оставить сообщения.
    assert await db.get_history(USER_A, limit=20) == []

    # Неудачный обмен не должен оставить файлы изображений.
    remaining_files = list(db.images_dir.iterdir())

    expected_empty = []
    assert remaining_files == expected_empty, "expected an empty list"
