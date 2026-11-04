import aiosqlite
import pytest

from bot.services.database.connection import open_connection
from bot.services.database.migrations.admin_ids import migrate_admin_ids
from bot.services.database.schema import create_schema


@pytest.mark.asyncio
async def test_create_schema_is_idempotent():
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
        } <= tables
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_admin_ids_migration_runs_once_and_excludes_supervisor():
    connection = await aiosqlite.connect(":memory:")

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
            "SELECT name FROM app_migrations WHERE name = ?",
            ("migrate_admin_ids_to_sqlite",),
        )
        assert await cursor.fetchone() is not None
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_open_connection_applies_existing_sqlite_pragmas():
    connection = await open_connection(":memory:")

    try:
        assert connection.row_factory is aiosqlite.Row

        cursor = await connection.execute("PRAGMA foreign_keys")
        assert (await cursor.fetchone())[0] == 1

        cursor = await connection.execute("PRAGMA busy_timeout")
        assert (await cursor.fetchone())[0] == 5000
    finally:
        await connection.close()
