# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the database facade connection lifecycle."""

from pathlib import Path

import pytest

from bot_obormot.services.database import Database
from tests.support.settings import make_settings


@pytest.mark.asyncio
async def test_database_context_manager_connects_and_closes(
    tmp_path: Path,
) -> None:
    settings = make_settings(DATABASE_PATH=str(tmp_path / "context.db"))
    database = Database(settings)

    async with database as entered_database:
        assert entered_database is database
        assert database.connection is not None
        assert await database.health_check()

    assert database.connection is None


@pytest.mark.asyncio
async def test_database_context_manager_closes_after_exception(
    tmp_path: Path,
) -> None:
    settings = make_settings(DATABASE_PATH=str(tmp_path / "context_error.db"))
    database = Database(settings)

    async def fail_inside_context() -> None:
        async with database:
            assert database.connection is not None
            msg = "context failure"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="context failure"):
        await fail_inside_context()

    assert database.connection is None


def test_database_images_dir_uses_injected_settings_at_instance_creation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "custom" / "history.db"
    settings = make_settings(DATABASE_PATH=str(database_path))

    database = Database(settings)

    assert database.images_dir == database_path.resolve().parent / "images"


def test_database_instance_does_not_create_files_before_connect(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "not-created" / "history.db"
    settings = make_settings(DATABASE_PATH=str(database_path))

    Database(settings)

    assert not database_path.parent.exists()
