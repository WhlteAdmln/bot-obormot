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
    assert not list(test_db.images_dir.iterdir())
    # Успешный следующий запрос доказывает, что lock был освобождён.
    assert await test_db.health_check() is True


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
    assert not list(test_db.images_dir.iterdir())
