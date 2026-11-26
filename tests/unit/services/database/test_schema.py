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


async def _migrate_twice(connection: aiosqlite.Connection) -> None:
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


@pytest.mark.asyncio
async def test_create_schema_is_idempotent() -> None:
    expected_tables = {
        "messages",
        "user_settings",
        "user_history_limits",
        "admins",
        "app_migrations",
        "message_media",
        "blocked_users",
    }
    async with aiosqlite.connect(":memory:") as connection:
        await create_schema(connection)
        await create_schema(connection)
        cursor = await connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
        tables = {row[0] for row in await cursor.fetchall()}
    assert expected_tables <= tables, "a second schema run lost a table"


@pytest.mark.asyncio
async def test_admin_ids_migration_runs_once_and_excludes_supervisor(
    tmp_path: Path,
) -> None:
    expected_ids = {101, 202}
    async with _connection(str(tmp_path / "admin_ids.db")) as connection:
        await _migrate_twice(connection)
        cursor = await connection.execute("SELECT user_id FROM admins")
        admin_ids = {row[0] for row in await cursor.fetchall()}
    assert admin_ids == expected_ids, "the migrated administrators differ"


@pytest.mark.asyncio
async def test_admin_ids_migration_is_recorded_once(tmp_path: Path) -> None:
    migration_name = "migrate_admin_ids_to_sqlite"
    expected_number = 1
    async with _connection(str(tmp_path / "admin_ids_record.db")) as connection:
        await _migrate_twice(connection)
        cursor = await connection.execute(
            "SELECT COUNT(*) AS total FROM app_migrations WHERE name = ?",
            (migration_name,),
        )
        row = await cursor.fetchone()
    total = None if row is None else row["total"]
    assert total == expected_number, "the migration is not recorded exactly once"


@pytest.mark.asyncio
async def test_open_connection_sets_the_row_factory() -> None:
    async with _connection(":memory:") as connection:
        row_factory = connection.row_factory
    assert row_factory is aiosqlite.Row, "the connection does not return Row objects"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("pragma", "expected_number"),
    [("foreign_keys", 1), ("busy_timeout", 5000)],
)
async def test_open_connection_applies_existing_sqlite_pragmas(
    pragma: str,
    expected_number: int,
) -> None:
    async with _connection(":memory:") as connection:
        cursor = await connection.execute(f"PRAGMA {pragma}")
        row = await cursor.fetchone()
    value = None if row is None else row[0]
    assert value == expected_number, f"the {pragma} pragma has another value"
