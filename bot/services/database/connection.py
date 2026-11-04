"""Создание и настройка SQLite-соединения."""

import aiosqlite


async def open_connection(database_path: str) -> aiosqlite.Connection:
    """Открывает SQLite-соединение с настройками приложения."""

    connection = await aiosqlite.connect(
        database_path,
        timeout=5.0,
    )

    connection.row_factory = aiosqlite.Row

    # Настройки SQLite.
    await connection.execute("PRAGMA foreign_keys = ON")
    await connection.execute("PRAGMA busy_timeout = 5000")
    await connection.execute("PRAGMA journal_mode = WAL")

    return connection
