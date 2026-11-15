# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database schema."""

import asyncio
from pathlib import Path

import aiosqlite
import pytest

from bot.services.database.connection import open_connection
from bot.services.database.migrations.admin_ids import migrate_admin_ids
from bot.services.database.schema import create_schema


@pytest.mark.asyncio
async def test_create_schema_is_idempotent() -> None:
    """Create schema is idempotent."""
    connection = await aiosqlite.connect(":memory:")

    try:
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
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_admin_ids_migration_runs_once_and_excludes_supervisor(
    tmp_path: Path,
) -> None:
    """Admin ids migration runs once and excludes supervisor."""
    connection = await open_connection(str(tmp_path / "admin_ids.db"))

    try:
        await create_schema(connection)
        await migrate_admin_ids(
            connection,
            admin_ids={101, 202, 999},
            supervisor_id=999,
        )
        await connection.commit()

        # Изменённая конфигурация не должна повторно запускать миграцию.
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
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_open_previous_schema_database_preserves_existing_data(
    tmp_path: Path,
) -> None:
    """Opening a previous schema database preserves data and adds new tables."""
    database_path = tmp_path / "previous-schema.db"
    fixtures_dir = Path(__file__).parent.parent / "fixtures"
    fixture_path = fixtures_dir / "previous_database_schema.sql"
    fixture_sql = await asyncio.to_thread(
        fixture_path.read_text,
        encoding="utf-8",
    )

    legacy_connection = await aiosqlite.connect(str(database_path))
    try:
        await legacy_connection.executescript(fixture_sql)
        await legacy_connection.commit()
    finally:
        await legacy_connection.close()

    connection = await open_connection(str(database_path))
    try:
        await create_schema(connection)

        cursor = await connection.execute(
            "SELECT role, content FROM messages WHERE user_id = ?",
            (424242,),
        )
        message = await cursor.fetchone()
        assert message is not None
        assert (message["role"], message["content"]) == (
            "user",
            "Legacy message",
        )

        cursor = await connection.execute(
            "SELECT system_prompt FROM user_settings WHERE user_id = ?",
            (424242,),
        )
        assert (await cursor.fetchone())["system_prompt"] == "Legacy prompt"

        cursor = await connection.execute(
            "SELECT exchange_limit FROM user_history_limits WHERE user_id = ?",
            (424242,),
        )
        assert (await cursor.fetchone())["exchange_limit"] == 7

        cursor = await connection.execute(
            "SELECT file_path FROM message_media WHERE message_id = ?",
            (1,),
        )
        assert (await cursor.fetchone())["file_path"] == ("/legacy/images/legacy.jpg")

        cursor = await connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'blocked_users'
            """
        )
        assert await cursor.fetchone() is not None
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_open_connection_applies_existing_sqlite_pragmas() -> None:
    """Open connection applies existing sqlite pragmas."""
    connection = await open_connection(":memory:")

    try:
        assert connection.row_factory is aiosqlite.Row

        cursor = await connection.execute("PRAGMA foreign_keys")
        assert (await cursor.fetchone())[0] == 1

        cursor = await connection.execute("PRAGMA busy_timeout")
        assert (await cursor.fetchone())[0] == 5000
    finally:
        await connection.close()
