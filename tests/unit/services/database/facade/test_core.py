# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the database facade connection lifecycle."""

from pathlib import Path

import pytest

from bot_obormot.services.database import Database
from tests.support.settings import make_settings


def _database(path: Path) -> Database:
    return Database(make_settings(DATABASE_PATH=str(path)))


@pytest.mark.asyncio
async def test_database_context_manager_returns_the_database(tmp_path: Path) -> None:
    database = _database(tmp_path / "context.db")

    async with database as entered_database:
        is_same = entered_database is database

    assert is_same is True, "the context manager entered another object"


@pytest.mark.asyncio
async def test_database_context_manager_connects(tmp_path: Path) -> None:
    database = _database(tmp_path / "connected.db")

    async with database:
        connected = database.connection is not None

    assert connected is True, "the database was not connected inside the context"


@pytest.mark.asyncio
async def test_database_context_manager_passes_health_check(tmp_path: Path) -> None:
    database = _database(tmp_path / "healthy.db")

    async with database:
        healthy = await database.health_check()

    assert healthy is True, "the connected database failed the health check"


@pytest.mark.asyncio
async def test_database_context_manager_closes_on_exit(tmp_path: Path) -> None:
    database = _database(tmp_path / "closed.db")

    async with database:
        pass

    assert database.connection is None, "the database stayed connected after exit"


@pytest.mark.asyncio
async def test_database_context_manager_connects_before_an_exception(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path / "context_raised.db")
    connected: list[bool] = []

    async def fail_inside_context() -> None:
        async with database:
            connected.append(database.connection is not None)
            msg = "failure inside the context"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="failure inside the context"):
        await fail_inside_context()

    expected = [True]
    assert connected == expected, "the database was not connected inside the context"


@pytest.mark.asyncio
async def test_database_context_manager_closes_after_exception(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path / "context_error.db")

    async def fail_inside_context() -> None:
        async with database:
            msg = "context failure"
            raise RuntimeError(msg)

    with pytest.raises(RuntimeError, match="context failure"):
        await fail_inside_context()

    assert database.connection is None, "an exception left the database connected"


def test_database_images_dir_uses_injected_settings_at_instance_creation(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "custom" / "history.db"

    database = _database(database_path)

    expected = database_path.resolve().parent / "images"
    assert database.images_dir == expected, "the images dir ignores the settings"


def test_database_instance_does_not_create_files_before_connect(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "not-created" / "history.db"

    _database(database_path)

    exists = database_path.parent.exists()
    assert exists is False, "the database created files before connecting"
