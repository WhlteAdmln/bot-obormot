# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Database facade that serializes access to the shared SQLite connection."""

import asyncio
import logging
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self, cast

from bot_obormot.errors import DatabaseError
from bot_obormot.services.database.connection import open_connection
from bot_obormot.services.database.decorators import handle_database_errors
from bot_obormot.services.database.files.image_storage import (
    delete_image,
    is_managed_image,
    read_image_as_base64,
)
from bot_obormot.services.database.migrations.admin_ids import migrate_admin_ids
from bot_obormot.services.database.repositories import (
    admins as admins_repository,
)
from bot_obormot.services.database.repositories import (
    blocked_users as blocked_users_repository,
)
from bot_obormot.services.database.repositories import (
    history_limits as history_limits_repository,
)
from bot_obormot.services.database.repositories import (
    messages as messages_repository,
)
from bot_obormot.services.database.repositories import (
    user_settings as user_settings_repository,
)
from bot_obormot.services.database.schema import create_schema
from bot_obormot.services.database.usecases import exchange as exchange_usecase
from bot_obormot.services.database.usecases.cleanup import (
    cleanup_old_images as cleanup_old_images_usecase,
)
from bot_obormot.services.database.usecases.history import (
    get_history as get_history_usecase,
)
from bot_obormot.services.database.usecases.history import (
    reset_history as reset_history_usecase,
)
from bot_obormot.settings import Settings

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# Maximum number of media messages in history; all frames are loaded together.
MAX_HISTORY_MEDIA_MESSAGES = 3


class Database:  # pylint: disable=too-many-public-methods  # facade over use cases
    """Facade over the SQLite repositories and use cases."""

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

    @handle_database_errors
    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
    ) -> None:
        """Add an individual message to history."""
        await messages_repository.add_message(
            self._conn,
            user_id,
            role,
            content,
        )

    async def add_exchange(
        self,
        user_id: int,
        user_text: str,
        assistant_text: str,
        media: list[bytes] | None = None,
    ) -> None:
        """Atomically save a message exchange and its images."""
        await exchange_usecase.add_exchange(
            exchange_usecase.ExchangeContext(
                connection=self._conn,
                lock=self._lock,
                images_dir=self.images_dir,
                logger=logger,
            ),
            user_id,
            user_text,
            assistant_text=assistant_text,
            media=media,
        )

    @handle_database_errors
    async def prune_history(self, user_id: int) -> None:
        """Limit the number of stored messages for a user."""
        paths = await messages_repository.prune_user_history(
            self._conn,
            user_id,
            self.settings.MAX_STORED_EXCHANGES * 2,
        )

        for file_path in paths:
            image_path = Path(file_path)
            if is_managed_image(image_path, self.images_dir):
                await asyncio.to_thread(delete_image, image_path)

    @handle_database_errors
    async def get_history(
        self,
        user_id: int,
        limit: int | None = None,
        max_images: int = MAX_HISTORY_MEDIA_MESSAGES,
    ) -> list[dict[str, Any]]:
        """Load the most recent complete exchanges for a user."""
        return await get_history_usecase(
            self._conn,
            user_id,
            limit,
            max_images,
            read_image_as_base64,
            logger,
        )

    @handle_database_errors
    async def cleanup_old_images(
        self,
        retention_days: int = 30,
        orphan_grace_hours: int = 24,
    ) -> dict[str, int]:
        """Delete old images and files that are not associated with the database."""
        return await cleanup_old_images_usecase(
            self._conn,
            self.images_dir,
            retention_days,
            orphan_grace_hours,
            logger,
            delete_image,
        )

    @handle_database_errors
    async def reset_history(self, user_id: int) -> None:
        """Delete a user's history and associated images."""
        await reset_history_usecase(
            self._conn,
            user_id,
            delete_image,
            logger,
            images_dir=self.images_dir,
        )

    @handle_database_errors
    async def forget_user(self, user_id: int) -> None:
        """Delete a user's history, personal prompt, and individual limit."""
        # Call the use case and repositories directly because nested facade
        # methods would attempt to acquire the same asyncio.Lock again.
        await reset_history_usecase(
            self._conn,
            user_id,
            delete_image,
            logger,
            images_dir=self.images_dir,
        )
        await user_settings_repository.delete_system_prompt(
            self._conn,
            user_id,
        )
        await history_limits_repository.delete_history_limit(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def get_system_prompt(self, user_id: int) -> str:
        """Return the personal prompt or the default system prompt."""
        prompt = await user_settings_repository.get_system_prompt(
            self._conn,
            user_id,
        )
        return prompt if prompt is not None else self.settings.DEFAULT_SYSTEM_PROMPT

    @handle_database_errors
    async def get_user_system_prompt(self, user_id: int) -> str | None:
        """Return the user's personal prompt or None."""
        return await user_settings_repository.get_system_prompt(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def delete_system_prompt(self, user_id: int) -> None:
        """Delete the user's personal system prompt."""
        await user_settings_repository.delete_system_prompt(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def set_system_prompt(
        self,
        user_id: int,
        prompt: str,
    ) -> None:
        """Save the user's personal system prompt."""
        await user_settings_repository.set_system_prompt(
            self._conn,
            user_id,
            prompt,
        )

    @handle_database_errors
    async def get_history_limit(self, user_id: int) -> int:
        """Return the individual history limit or the default value."""
        exchange_limit = await history_limits_repository.get_history_limit(
            self._conn,
            user_id,
        )
        return (
            self.settings.DEFAULT_HISTORY_EXCHANGES
            if exchange_limit is None
            else exchange_limit
        )

    @handle_database_errors
    async def set_history_limit(
        self,
        user_id: int,
        exchange_limit: int,
    ) -> None:
        """Set the individual history limit."""
        if not 1 <= exchange_limit <= self.settings.MAX_HISTORY_EXCHANGES:
            msg = "Invalid history limit."
            raise ValueError(msg)

        await history_limits_repository.set_history_limit(
            self._conn,
            user_id,
            exchange_limit,
        )

    @handle_database_errors
    async def delete_history_limit(self, user_id: int) -> None:
        """Delete the individual history limit."""
        await history_limits_repository.delete_history_limit(
            self._conn,
            user_id,
        )

    # --------------------------------------------------
    # Administrator management
    # --------------------------------------------------

    @handle_database_errors
    async def get_admin_ids(self) -> set[int]:
        """Return the IDs of regular administrators from SQLite."""
        return await admins_repository.get_admin_ids(self._conn)

    @handle_database_errors
    async def add_admin(self, user_id: int) -> bool:
        """Add a regular administrator."""
        if user_id == self.settings.SUPERVISOR_ID:
            return False

        return await admins_repository.add_admin(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def remove_admin(self, user_id: int) -> bool:
        """Remove a regular administrator."""
        if user_id == self.settings.SUPERVISOR_ID:
            return False

        return await admins_repository.remove_admin(
            self._conn,
            user_id,
        )

    # --------------------------------------------------
    # User blocking
    # --------------------------------------------------

    @handle_database_errors
    async def get_blocked_ids(self) -> set[int]:
        """Return the IDs of blocked users."""
        return await blocked_users_repository.get_blocked_ids(self._conn)

    @handle_database_errors
    async def block_user(self, user_id: int) -> bool:
        """Block a user, except for the supervisor."""
        if user_id == self.settings.SUPERVISOR_ID:
            return False
        return await blocked_users_repository.block_user(self._conn, user_id)

    @handle_database_errors
    async def unblock_user(self, user_id: int) -> bool:
        """Unblock a user."""
        return await blocked_users_repository.unblock_user(self._conn, user_id)


__all__ = ["MAX_HISTORY_MEDIA_MESSAGES", "Database"]
