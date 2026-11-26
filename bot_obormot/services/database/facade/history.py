# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Conversation history operations of the database facade."""

import asyncio
from pathlib import Path

from bot_obormot.common.llm_messages import ChatMessage
from bot_obormot.services.database.decorators import handle_database_errors
from bot_obormot.services.database.facade.core import DatabaseCore, logger
from bot_obormot.services.database.files.image_storage import (
    delete_image,
    is_managed_image,
    read_image_as_base64,
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

# Maximum number of media messages in history; all frames are loaded together.
MAX_HISTORY_MEDIA_MESSAGES = 3


class HistoryOperations(DatabaseCore):
    """Messages, exchanges, their images and the removal of a user's data."""

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
    ) -> list[ChatMessage]:
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


__all__ = ["MAX_HISTORY_MEDIA_MESSAGES", "HistoryOperations"]
