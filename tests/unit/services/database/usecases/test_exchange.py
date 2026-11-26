# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for usecases exchange."""

from pathlib import Path

import aiosqlite
import pytest

from bot_obormot.errors import DatabaseError, MediaError
from bot_obormot.services.database import Database
from bot_obormot.services.database.usecases import exchange as exchange_usecase
from tests.support.database_usecases import USER_ID


async def _reject_assistant_messages(test_db: Database) -> None:
    """Make the database refuse to store assistant messages."""
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


async def _fail_exchange_with_media(test_db: Database) -> None:
    """Try to save an exchange with an image that the database rejects."""
    await _reject_assistant_messages(test_db)
    with pytest.raises(DatabaseError, match="Could not save message exchange"):
        await test_db.add_exchange(
            USER_ID,
            "Вопрос с картинкой",
            "Ответ про картинку",
            media=[b"image-bytes"],
        )


async def _fail_exchange_inside_transaction(test_db: Database) -> None:
    """Try to save an exchange while a foreign transaction is open."""
    await test_db.connection.execute("BEGIN")
    with pytest.raises(DatabaseError, match="Could not save message exchange"):
        await test_db.add_exchange(USER_ID, "Чужая транзакция?", "Да, чужая.")


async def _fail_exchange_and_rollback(
    test_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Try to save a rejected exchange while the rollback fails too."""
    await _reject_assistant_messages(test_db)
    original_rollback = test_db.connection.rollback

    async def fail_rollback() -> None:
        msg = "rollback failed"
        raise aiosqlite.OperationalError(msg)

    with monkeypatch.context() as patcher:
        patcher.setattr(test_db.connection, "rollback", fail_rollback)
        with pytest.raises(DatabaseError, match="Could not save message exchange"):
            await test_db.add_exchange(USER_ID, "Откат сломан?", "Похоже, да.")

    await original_rollback()


async def _fail_image_save_and_cleanup(
    test_db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Try to save an exchange while image saving and removal fail."""

    def fail_save_image(_image_path: Path, _image_data: bytes) -> None:
        msg = "disk full"
        raise OSError(msg)

    def fail_delete_image(_image_path: Path) -> None:
        msg = "permission denied"
        raise OSError(msg)

    monkeypatch.setattr(exchange_usecase, "save_image", fail_save_image)
    monkeypatch.setattr(exchange_usecase, "delete_image", fail_delete_image)

    with pytest.raises(MediaError, match="Could not save or remove media file"):
        await test_db.add_exchange(
            USER_ID,
            "Сохрани фото",
            "Не вышло",
            media=[b"png-bytes"],
        )


@pytest.mark.asyncio
async def test_add_exchange_rolls_back_messages(test_db: Database) -> None:
    await _fail_exchange_with_media(test_db)
    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM messages WHERE user_id = ?",
        (USER_ID,),
    )
    expected_total = 0
    row = await cursor.fetchone()
    assert row["total"] == expected_total, "the messages were not rolled back"


@pytest.mark.asyncio
async def test_add_exchange_rolls_back_media_rows(test_db: Database) -> None:
    await _fail_exchange_with_media(test_db)
    cursor = await test_db.connection.execute(
        "SELECT COUNT(*) AS total FROM message_media"
    )
    expected_total = 0
    row = await cursor.fetchone()
    assert row["total"] == expected_total, "the media rows were not rolled back"


@pytest.mark.asyncio
async def test_add_exchange_removes_saved_images_after_rollback(
    test_db: Database,
) -> None:
    await _fail_exchange_with_media(test_db)
    expected_empty: list[Path] = []
    images = list(test_db.images_dir.iterdir())
    assert images == expected_empty, "the saved images were not removed"


@pytest.mark.asyncio
async def test_add_exchange_keeps_database_healthy_after_rollback(
    test_db: Database,
) -> None:
    await _fail_exchange_with_media(test_db)
    healthy = await test_db.health_check()
    assert healthy is True, "the database is unhealthy after a rollback"


@pytest.mark.asyncio
async def test_add_exchange_does_not_rollback_transaction_it_did_not_start(
    test_db: Database,
) -> None:
    await _fail_exchange_inside_transaction(test_db)
    in_transaction = test_db.connection.in_transaction
    assert in_transaction is True, "the foreign transaction was rolled back"


@pytest.mark.asyncio
async def test_add_exchange_leaves_no_history_inside_foreign_transaction(
    test_db: Database,
) -> None:
    await _fail_exchange_inside_transaction(test_db)
    await test_db.connection.rollback()
    expected_empty: list[object] = []
    history = await test_db.get_history(USER_ID)
    assert history == expected_empty, "a failed exchange left history"


@pytest.mark.asyncio
async def test_add_exchange_handles_rollback_failure(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fail_exchange_and_rollback(test_db, monkeypatch)
    in_transaction = test_db.connection.in_transaction
    assert in_transaction is False, "a transaction is still open"


@pytest.mark.asyncio
async def test_add_exchange_leaves_no_history_after_rollback_failure(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fail_exchange_and_rollback(test_db, monkeypatch)
    expected_empty: list[object] = []
    history = await test_db.get_history(USER_ID)
    assert history == expected_empty, "a failed exchange left history"


@pytest.mark.asyncio
async def test_add_exchange_closes_transaction_after_image_failures(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fail_image_save_and_cleanup(test_db, monkeypatch)
    in_transaction = test_db.connection.in_transaction
    assert in_transaction is False, "a transaction is still open"


@pytest.mark.asyncio
async def test_add_exchange_leaves_no_history_after_image_failures(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fail_image_save_and_cleanup(test_db, monkeypatch)
    expected_empty: list[object] = []
    history = await test_db.get_history(USER_ID)
    assert history == expected_empty, "a failed exchange left history"


@pytest.mark.asyncio
async def test_add_exchange_leaves_no_images_after_image_failures(
    test_db: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _fail_image_save_and_cleanup(test_db, monkeypatch)
    expected_empty: list[Path] = []
    images = list(test_db.images_dir.iterdir())
    assert images == expected_empty, "an image file was left behind"
