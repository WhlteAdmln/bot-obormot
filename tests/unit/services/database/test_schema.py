# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database schema."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import pytest

from bot_obormot.services.database.connection import open_connection
from bot_obormot.services.database.migrations.admin_ids import migrate_admin_ids
from bot_obormot.services.database.schema import create_schema


@asynccontextmanager
async def _connection(path: str) -> AsyncIterator[aiosqlite.Connection]:
    connection = await open_connection(path)
    try:
        yield connection
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_create_schema_is_idempotent() -> None:
    async with aiosqlite.connect(":memory:") as connection:
        await create_schema(connection)
        await create_schema(connection)

        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        tables = {row[0] for row in await cursor.fetchall()}

        assert {
            "messages",
            "user_settings",
            "user_history_limits",
            "admins",
            "app_migrations",
            "message_media",
            "blocked_users",
        } <= tables


@pytest.mark.asyncio
async def test_admin_ids_migration_runs_once_and_excludes_supervisor(
    tmp_path: Path,
) -> None:
    async with _connection(str(tmp_path / "admin_ids.db")) as connection:
        await create_schema(connection)
        await migrate_admin_ids(
            connection,
            admin_ids={101, 202, 999},
            supervisor_id=999,
        )
        await connection.commit()

        await migrate_admin_ids(
            connection,
            admin_ids={303},
            supervisor_id=999,
        )
        await connection.commit()

        cursor = await connection.execute("SELECT user_id FROM admins")
        admin_ids = {row[0] for row in await cursor.fetchall()}

        assert admin_ids == {101, 202}

        cursor = await connection.execute(
            "SELECT COUNT(*) AS total FROM app_migrations WHERE name = ?",
            ("migrate_admin_ids_to_sqlite",),
        )
        assert (await cursor.fetchone())["total"] == 1


@pytest.mark.asyncio
async def test_open_connection_applies_existing_sqlite_pragmas() -> None:
    async with _connection(":memory:") as connection:
        assert connection.row_factory is aiosqlite.Row

        cursor = await connection.execute("PRAGMA foreign_keys")
        assert (await cursor.fetchone())[0] == 1

        cursor = await connection.execute("PRAGMA busy_timeout")
        expected_number = 5000
        assert (await cursor.fetchone())[0] == expected_number
