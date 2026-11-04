"""Перенос обычных администраторов из конфигурации в SQLite."""

import logging

import aiosqlite


logger = logging.getLogger("bot.services.database.facade")
MIGRATION_NAME = "migrate_admin_ids_to_sqlite"


async def migrate_admin_ids(
    connection: aiosqlite.Connection,
    admin_ids: set[int],
    supervisor_id: int,
) -> None:
    """Однократно переносит ADMIN_IDS, исключая Supervisor."""

    cursor = await connection.execute(
        """
        SELECT name
        FROM app_migrations
        WHERE name = ?
        """,
        (MIGRATION_NAME,),
    )

    migration = await cursor.fetchone()

    if migration is None:
        ordinary_admin_ids = admin_ids - {supervisor_id}

        if ordinary_admin_ids:
            await connection.executemany(
                """
                INSERT OR IGNORE INTO admins(user_id)
                VALUES (?)
                """,
                [(user_id,) for user_id in ordinary_admin_ids],
            )

        await connection.execute(
            """
            INSERT INTO app_migrations(name)
            VALUES (?)
            """,
            (MIGRATION_NAME,),
        )

        logger.info(
            "Migrated %s administrator IDs from configuration to SQLite",
            len(ordinary_admin_ids),
        )
