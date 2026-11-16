# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Create and configure SQLite connections."""

import aiosqlite


async def open_connection(database_path: str) -> aiosqlite.Connection:
    """Open a SQLite connection with application settings."""
    connection = await aiosqlite.connect(
        database_path,
        timeout=5.0,
    )

    connection.row_factory = aiosqlite.Row

    # SQLite settings.
    await connection.execute("PRAGMA foreign_keys = ON")
    await connection.execute("PRAGMA busy_timeout = 5000")
    await connection.execute("PRAGMA journal_mode = WAL")

    return connection
