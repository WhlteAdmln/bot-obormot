# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Connection lifecycle shared by the parts of the database facade."""

import asyncio
import logging
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Self, cast

from bot_obormot.errors import DatabaseError
from bot_obormot.services.database.connection import open_connection
from bot_obormot.services.database.decorators import handle_database_errors
from bot_obormot.services.database.migrations.admin_ids import migrate_admin_ids
from bot_obormot.services.database.schema import create_schema
from bot_obormot.settings import Settings

if TYPE_CHECKING:
    import aiosqlite

# Keep the previous logger name to preserve log routing.
logger = logging.getLogger("bot_obormot.services.database.facade")


class DatabaseCore:
    """Owns the SQLite connection, its lock and the images directory."""

    def __init__(self, settings: Settings) -> None:
        """Prepares the images directory path and the connection lock."""
        self.connection: aiosqlite.Connection | None = None
        self.settings = settings

        self.images_dir = Path(settings.DATABASE_PATH).resolve().parent / "images"

        # Protect the shared SQLite connection from concurrent access.
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> Self:
        """Open the database connection and return this instance."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the database connection after leaving the context."""
        _ = exc_type, exc_value
        await self.close()

    def configure(self, settings: Settings) -> None:
        """Apply application settings before opening the connection."""
        if self.connection is not None:
            msg = "Cannot configure database while connected"
            raise RuntimeError(msg)

        self.settings = settings
        self.images_dir = Path(settings.DATABASE_PATH).resolve().parent / "images"

    @property
    def _conn(self) -> "aiosqlite.Connection":
        """Returns the open connection; ``connect`` must have been called."""
        return cast("aiosqlite.Connection", self.connection)

    @handle_database_errors
    async def connect(self) -> None:
        """Create the connection, tables, and run migrations."""
        Path(self.settings.DATABASE_PATH).parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.connection = await open_connection(self.settings.DATABASE_PATH)

        await create_schema(self.connection)
        await migrate_admin_ids(
            self.connection,
            self.settings.ADMIN_IDS,
            self.settings.SUPERVISOR_ID,
        )

        await self.connection.commit()

        logger.info("SQLite database initialized")

    @handle_database_errors
    async def close(self) -> None:
        """Close the database connection."""
        if self.connection:
            await self.connection.close()
            self.connection = None

    @handle_database_errors
    async def health_check(self) -> bool:
        """Check SQLite availability."""
        if self.connection is None:
            msg = "Database connection is not initialized"
            raise DatabaseError(msg)

        cursor = await self.connection.execute("SELECT 1")
        row = await cursor.fetchone()

        return bool(row is not None and row[0] == 1)


__all__ = ["DatabaseCore", "logger"]
