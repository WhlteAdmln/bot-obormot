# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the history operations of the database facade."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest

from bot_obormot.errors import DatabaseError
from bot_obormot.services.database import Database


async def _latest_image_path(db: Database) -> Path:
    cursor = await db.connection.execute(
        "SELECT file_path FROM message_media ORDER BY id DESC LIMIT 1"
    )
    return Path((await cursor.fetchone())["file_path"])


async def _image_path_of(db: Database, user_id: int) -> Path:
    cursor = await db.connection.execute(
        "SELECT mm.file_path FROM message_media mm "
        "JOIN messages m ON m.id = mm.message_id WHERE m.user_id = ?",
        (user_id,),
    )
    return Path((await cursor.fetchone())["file_path"])


async def _attach_external_image(db: Database, user_id: int, image: Path) -> None:
    cursor = await db.connection.execute(
        "SELECT id FROM messages WHERE user_id = ? ORDER BY id LIMIT 1",
        (user_id,),
    )
    first_message_id = (await cursor.fetchone())["id"]
    await db.connection.execute(
        "INSERT INTO message_media(message_id, file_path, mime_type) "
        "VALUES (?, ?, 'image/jpeg')",
        (first_message_id, str(image)),
    )
    await db.connection.commit()


async def _prune_scenario(
    db: Database, user_id: int, other_user_id: int, external_image: Path
) -> tuple[Path, Path]:
    db.settings = replace(db.settings, MAX_STORED_EXCHANGES=2)
    await asyncio.to_thread(external_image.write_bytes, b"must not be deleted")
    old_image = latest_image = external_image
    for number in range(5):
        media = [f"image-{number}".encode()] if number in {0, 4} else None
        await db.add_exchange(
            user_id, f"Вопрос {number}", f"Ответ {number}", media=media
        )
        if number == 0:
            old_image = await _latest_image_path(db)
            await _attach_external_image(db, user_id, external_image)
        elif media is not None:
            latest_image = await _latest_image_path(db)
    for number in range(5):
        await db.add_exchange(
            other_user_id, f"Другой вопрос {number}", f"Другой ответ {number}"
        )
    await db.prune_history(user_id)
    return old_image, latest_image


async def _store_two_users(
    db: Database, user_id: int, other_user_id: int
) -> tuple[Path, Path]:
    await db.set_system_prompt(user_id, "Персональный промпт")
    await db.set_history_limit(user_id, 17)
    await db.add_exchange(user_id, "Мой вопрос", "Мой ответ", media=[b"my-image"])
    await db.set_system_prompt(other_user_id, "Чужой промпт")
    await db.set_history_limit(other_user_id, 23)
    await db.add_exchange(
        other_user_id, "Чужой вопрос", "Чужой ответ", media=[b"other-image"]
    )
    own_image = await _image_path_of(db, user_id)
    other_image = await _image_path_of(db, other_user_id)
    return own_image, other_image


async def _forget_scenario(
    db: Database, user_id: int, other_user_id: int
) -> tuple[Path, Path]:
    images = await _store_two_users(db, user_id, other_user_id)
    await db.forget_user(user_id)
    return images


@pytest.mark.asyncio
async def test_history_limit_counts_complete_exchanges(test_db: Database) -> None:
    user_id = 111111111
    for number in range(5):
        await test_db.add_exchange(user_id, f"Вопрос {number}", f"Ответ {number}")
    history = await test_db.get_history(user_id, limit=2)
    expected_count = 4
    assert len(history) == expected_count, "the limit must count exchanges"


@pytest.mark.asyncio
async def test_history_limit_returns_the_latest_exchanges(test_db: Database) -> None:
    user_id = 202020202
    for number in range(5):
        await test_db.add_exchange(user_id, f"Вопрос {number}", f"Ответ {number}")
    history = await test_db.get_history(user_id, limit=2)
    expected = ["Вопрос 3", "Ответ 3", "Вопрос 4", "Ответ 4"]
    actual = [item["content"] for item in history]
    assert actual == expected, "the history is not the latest exchanges"


@pytest.mark.asyncio
async def test_history_limit_zero_returns_empty_history(test_db: Database) -> None:
    user_id = 31337
    await test_db.add_exchange(user_id, "Сколько времени?", "Без пяти полночь")
    expected_empty: list[dict[str, object]] = []
    history = await test_db.get_history(user_id, limit=0)
    assert history == expected_empty, "a zero limit must return no history"


@pytest.mark.asyncio
async def test_history_ignores_incomplete_messages_in_the_count(
    test_db: Database,
) -> None:
    user_id = 111111111
    await test_db.add_exchange(user_id, "Вопрос 1", "Ответ 1")
    await test_db.add_message(user_id, "user", "Незавершённый вопрос")
    history = await test_db.get_history(user_id, limit=10)
    expected_count = 2
    assert len(history) == expected_count, "an incomplete message was counted"


@pytest.mark.asyncio
async def test_history_ignores_incomplete_messages(test_db: Database) -> None:
    user_id = 404040404
    await test_db.add_exchange(user_id, "Где ключи?", "В прихожей")
    await test_db.add_message(user_id, "user", "Оборванный вопрос")
    history = await test_db.get_history(user_id, limit=10)
    expected = ["Где ключи?", "В прихожей"]
    actual = [item["content"] for item in history]
    assert actual == expected, "an incomplete message is in the history"


@pytest.mark.asyncio
async def test_history_limit_is_stored_per_user(test_db: Database) -> None:
    user_id = 111111111
    other_user_id = 111111112
    await test_db.set_history_limit(user_id, 10)
    await test_db.set_history_limit(other_user_id, 5)
    expected_limit = 10
    actual = await test_db.get_history_limit(user_id)
    assert actual == expected_limit, "the first user's limit changed"


@pytest.mark.asyncio
async def test_history_limit_is_isolated_between_users(test_db: Database) -> None:
    user_id = 515151515
    other_user_id = 515151516
    await test_db.set_history_limit(user_id, 12)
    await test_db.set_history_limit(other_user_id, 5)
    expected_limit = 5
    actual = await test_db.get_history_limit(other_user_id)
    assert actual == expected_limit, "the second user's limit changed"


@pytest.mark.asyncio
async def test_history_limit_defaults_for_a_user_without_one(
    test_db: Database,
) -> None:
    user_id = 616161616
    await test_db.set_history_limit(user_id, 10)
    await test_db.set_history_limit(user_id + 1, 5)
    expected_limit = test_db.settings.DEFAULT_HISTORY_EXCHANGES
    actual = await test_db.get_history_limit(user_id + 2)
    assert actual == expected_limit, "an unknown user must get the default limit"


@pytest.mark.asyncio
async def test_prune_history_keeps_latest_exchanges(
    test_db: Database, tmp_path: Path
) -> None:
    user_id = 111111111
    await _prune_scenario(test_db, user_id, 111111112, tmp_path / "external.jpg")
    cursor = await test_db.connection.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id",
        (user_id,),
    )
    expected = [
        ("user", "Вопрос 3"),
        ("assistant", "Ответ 3"),
        ("user", "Вопрос 4"),
        ("assistant", "Ответ 4"),
    ]
    actual = [(row["role"], row["content"]) for row in await cursor.fetchall()]
    assert actual == expected, "pruning kept wrong messages"


@pytest.mark.asyncio
async def test_prune_history_keeps_other_users(
    test_db: Database, tmp_path: Path
) -> None:
    other_user_id = 707070708
    await _prune_scenario(test_db, 707070707, other_user_id, tmp_path / "photo.jpg")
    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM messages WHERE user_id = ?",
        (other_user_id,),
    )
    expected_total = 10
    actual = (await cursor.fetchone())["total"]
    assert actual == expected_total, "pruning touched another user's history"


@pytest.mark.asyncio
async def test_prune_history_removes_old_images(
    test_db: Database, tmp_path: Path
) -> None:
    old_image, _ = await _prune_scenario(
        test_db, 818181818, 818181819, tmp_path / "outside.jpg"
    )
    exists = old_image.exists()
    assert exists is False, "the image of a pruned exchange was kept"


@pytest.mark.asyncio
async def test_prune_history_keeps_latest_images(
    test_db: Database, tmp_path: Path
) -> None:
    _, latest_image = await _prune_scenario(
        test_db, 929292929, 929292930, tmp_path / "foreign.jpg"
    )
    assert latest_image.exists(), "the image of a kept exchange was removed"


@pytest.mark.asyncio
async def test_prune_history_keeps_external_files(
    test_db: Database, tmp_path: Path
) -> None:
    external_image = tmp_path / "external-old-image.jpg"
    await _prune_scenario(test_db, 123123123, 123123124, external_image)
    expected_bytes = b"must not be deleted"
    actual = external_image.read_bytes()
    assert actual == expected_bytes, "pruning deleted a file outside the images dir"


@pytest.mark.asyncio
async def test_prune_history_keeps_media_rows_of_latest_exchanges(
    test_db: Database, tmp_path: Path
) -> None:
    user_id = 456456456
    await _prune_scenario(test_db, user_id, 456456457, tmp_path / "elsewhere.jpg")
    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM message_media mm "
        "JOIN messages m ON m.id = mm.message_id WHERE m.user_id = ?",
        (user_id,),
    )
    actual = (await cursor.fetchone())["total"]
    assert actual == 1, "pruning kept wrong media rows"


@pytest.mark.asyncio
async def test_add_exchange_stores_the_own_image_before_forgetting(
    test_db: Database,
) -> None:
    own_image, _ = await _store_two_users(test_db, 111111131, 111111132)
    assert await asyncio.to_thread(own_image.exists), "the own image was not stored"


@pytest.mark.asyncio
async def test_add_exchange_stores_the_other_image_before_forgetting(
    test_db: Database,
) -> None:
    _, other_image = await _store_two_users(test_db, 222222241, 222222242)
    exists = await asyncio.to_thread(other_image.exists)
    assert exists, "the other user's image was not stored"


@pytest.mark.asyncio
async def test_forget_user_removes_the_personal_prompt(test_db: Database) -> None:
    user_id = 333333351
    await _forget_scenario(test_db, user_id, 333333352)
    prompt = await test_db.get_user_system_prompt(user_id)
    assert prompt is None, "the personal prompt was kept"


@pytest.mark.asyncio
async def test_forget_user_restores_the_default_prompt(test_db: Database) -> None:
    user_id = 444444461
    await _forget_scenario(test_db, user_id, 444444462)
    expected_prompt = test_db.settings.DEFAULT_SYSTEM_PROMPT
    actual = await test_db.get_system_prompt(user_id)
    assert actual == expected_prompt, "the default prompt was not restored"


@pytest.mark.asyncio
async def test_forget_user_restores_the_default_limit(test_db: Database) -> None:
    user_id = 555555571
    await _forget_scenario(test_db, user_id, 555555572)
    expected_limit = test_db.settings.DEFAULT_HISTORY_EXCHANGES
    actual = await test_db.get_history_limit(user_id)
    assert actual == expected_limit, "the default history limit was not restored"


@pytest.mark.asyncio
async def test_forget_user_removes_the_history(test_db: Database) -> None:
    user_id = 666666681
    await _forget_scenario(test_db, user_id, 666666682)
    expected_empty: list[dict[str, object]] = []
    history = await test_db.get_history(user_id)
    assert history == expected_empty, "the history was kept"


@pytest.mark.asyncio
async def test_forget_user_removes_owned_images(test_db: Database) -> None:
    own_image, _ = await _forget_scenario(test_db, 777777791, 777777792)
    exists = await asyncio.to_thread(own_image.exists)
    assert exists is False, "the owned image was kept"


@pytest.mark.asyncio
async def test_forget_user_keeps_the_other_prompt(test_db: Database) -> None:
    other_user_id = 888888802
    await _forget_scenario(test_db, 888888801, other_user_id)
    expected_prompt = "Чужой промпт"
    actual = await test_db.get_user_system_prompt(other_user_id)
    assert actual == expected_prompt, "another user's prompt changed"


@pytest.mark.asyncio
async def test_forget_user_keeps_the_other_limit(test_db: Database) -> None:
    other_user_id = 999999812
    await _forget_scenario(test_db, 999999811, other_user_id)
    expected_limit = 23
    actual = await test_db.get_history_limit(other_user_id)
    assert actual == expected_limit, "another user's limit changed"


@pytest.mark.asyncio
async def test_forget_user_keeps_the_other_question(test_db: Database) -> None:
    other_user_id = 101010122
    await _forget_scenario(test_db, 101010121, other_user_id)
    history = await test_db.get_history(other_user_id)
    expected_text = "Чужой вопрос"
    assert history[0]["content"][0]["text"] == expected_text, "the question changed"


@pytest.mark.asyncio
async def test_forget_user_keeps_the_other_image_part(test_db: Database) -> None:
    other_user_id = 121212132
    await _forget_scenario(test_db, 121212131, other_user_id)
    history = await test_db.get_history(other_user_id)
    expected_type = "image_url"
    assert history[0]["content"][1]["type"] == expected_type, "the image part changed"


@pytest.mark.asyncio
async def test_forget_user_keeps_the_other_answer(test_db: Database) -> None:
    other_user_id = 131313142
    await _forget_scenario(test_db, 131313141, other_user_id)
    history = await test_db.get_history(other_user_id)
    expected_content = "Чужой ответ"
    assert history[1]["content"] == expected_content, "the answer changed"


@pytest.mark.asyncio
async def test_forget_user_keeps_the_other_image(test_db: Database) -> None:
    _, other_image = await _forget_scenario(test_db, 141414151, 141414152)
    exists = await asyncio.to_thread(other_image.exists)
    assert exists, "another user's image was removed"


@pytest.mark.asyncio
async def test_rolls_back_failed_exchange(test_db: Database) -> None:
    user_id = 111111111
    with pytest.raises(DatabaseError):
        await test_db.add_exchange(
            user_id, "Тестовое сообщение", None, media=[b"fake-image-data"]
        )
    expected_empty: list[dict[str, object]] = []
    history = await test_db.get_history(user_id, limit=20)
    assert history == expected_empty, "a failed exchange left history"


@pytest.mark.asyncio
async def test_rolls_back_failed_exchange_with_its_images(test_db: Database) -> None:
    user_id = 161616161
    with pytest.raises(DatabaseError):
        await test_db.add_exchange(
            user_id, "Сообщение без ответа", None, media=[b"\xff\xd8broken-jpeg"]
        )
    expected_empty: list[Path] = []
    remaining_files = list(test_db.images_dir.iterdir())
    assert remaining_files == expected_empty, "a failed exchange left image files"
