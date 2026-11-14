# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Database facade that serializes access to the shared SQLite connection."""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from bot.config import config
from bot.errors import DatabaseError
from bot.services.database.connection import open_connection
from bot.services.database.decorators import handle_database_errors
from bot.services.database.files.image_storage import (
    delete_image,
    is_managed_image,
    read_image_as_base64,
)
from bot.services.database.migrations.admin_ids import migrate_admin_ids
from bot.services.database.repositories import (
    admins as admins_repository,
)
from bot.services.database.repositories import (
    blocked_users as blocked_users_repository,
)
from bot.services.database.repositories import (
    history_limits as history_limits_repository,
)
from bot.services.database.repositories import (
    messages as messages_repository,
)
from bot.services.database.repositories import (
    user_settings as user_settings_repository,
)
from bot.services.database.schema import create_schema
from bot.services.database.usecases import exchange as exchange_usecase
from bot.services.database.usecases.cleanup import (
    cleanup_old_images as cleanup_old_images_usecase,
)
from bot.services.database.usecases.history import (
    get_history as get_history_usecase,
)
from bot.services.database.usecases.history import (
    reset_history as reset_history_usecase,
)

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

# Максимум медиа-сообщений в истории; все кадры сообщения загружаются вместе.
MAX_HISTORY_MEDIA_MESSAGES = 3
# Старое имя оставлено для совместимости с публичными импортами.
MAX_HISTORY_IMAGES = MAX_HISTORY_MEDIA_MESSAGES


class Database:
    """Facade over the SQLite repositories and use cases."""

    def __init__(self) -> None:
        """Prepares the images directory path and the connection lock."""
        self.connection: aiosqlite.Connection | None = None

        self.images_dir = Path(config.DATABASE_PATH).resolve().parent / "images"

        # Защищает общее SQLite-соединение от конкурентного использования.
        self._lock = asyncio.Lock()

    @property
    def _conn(self) -> "aiosqlite.Connection":
        """Returns the open connection; ``connect`` must have been called."""
        return cast("aiosqlite.Connection", self.connection)

    @handle_database_errors
    async def connect(self) -> None:
        """Создаёт подключение, таблицы и выполняет миграции."""
        Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)

        self.images_dir.mkdir(parents=True, exist_ok=True)

        self.connection = await open_connection(config.DATABASE_PATH)

        await create_schema(self.connection)
        await migrate_admin_ids(
            self.connection,
            config.ADMIN_IDS,
            config.SUPERVISOR_ID,
        )

        await self.connection.commit()

        logger.info("SQLite database initialized")

    @handle_database_errors
    async def close(self) -> None:
        """Закрывает соединение с базой данных."""
        if self.connection:
            await self.connection.close()
            self.connection = None

    @handle_database_errors
    async def health_check(self) -> bool:
        """Проверяет доступность SQLite."""
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
        """Добавляет отдельное сообщение в историю."""
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
        """Атомарно сохраняет обмен сообщениями и изображения."""
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
        """Ограничивает число хранимых сообщений пользователя."""
        paths = await messages_repository.prune_user_history(
            self._conn,
            user_id,
            config.MAX_STORED_EXCHANGES * 2,
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
        """Загружает последние полные обмены пользователя."""
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
        """Удаляет старые изображения и файлы, не связанные с БД."""
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
        """Удаляет историю пользователя и связанные изображения."""
        await reset_history_usecase(
            self._conn,
            user_id,
            delete_image,
            logger,
            images_dir=self.images_dir,
        )

    @handle_database_errors
    async def forget_user(self, user_id: int) -> None:
        """Удаляет историю, персональный промпт и индивидуальный лимит пользователя."""
        # Вызываем use case и репозитории напрямую: вложенные методы фасада
        # повторно захватили бы тот же asyncio.Lock.
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
        """Возвращает персональный промпт или стандартный системный промпт."""
        prompt = await user_settings_repository.get_system_prompt(
            self._conn,
            user_id,
        )
        return prompt if prompt is not None else config.DEFAULT_SYSTEM_PROMPT

    @handle_database_errors
    async def get_user_system_prompt(self, user_id: int) -> str | None:
        """Возвращает персональный промпт пользователя или None."""
        return await user_settings_repository.get_system_prompt(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def delete_system_prompt(self, user_id: int) -> None:
        """Удаляет персональный системный промпт пользователя."""
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
        """Сохраняет персональный системный промпт пользователя."""
        await user_settings_repository.set_system_prompt(
            self._conn,
            user_id,
            prompt,
        )

    @handle_database_errors
    async def get_history_limit(self, user_id: int) -> int:
        """Возвращает индивидуальный лимит или стандартное значение."""
        exchange_limit = await history_limits_repository.get_history_limit(
            self._conn,
            user_id,
        )
        return (
            config.DEFAULT_HISTORY_EXCHANGES
            if exchange_limit is None
            else exchange_limit
        )

    @handle_database_errors
    async def set_history_limit(
        self,
        user_id: int,
        exchange_limit: int,
    ) -> None:
        """Устанавливает индивидуальный лимит истории."""
        if not 1 <= exchange_limit <= config.MAX_HISTORY_EXCHANGES:
            msg = "Недопустимый лимит истории."
            raise ValueError(msg)

        await history_limits_repository.set_history_limit(
            self._conn,
            user_id,
            exchange_limit,
        )

    @handle_database_errors
    async def delete_history_limit(self, user_id: int) -> None:
        """Удаляет индивидуальный лимит истории."""
        await history_limits_repository.delete_history_limit(
            self._conn,
            user_id,
        )

    # --------------------------------------------------
    # Управление администраторами
    # --------------------------------------------------

    @handle_database_errors
    async def get_admin_ids(self) -> set[int]:
        """Возвращает ID обычных администраторов из SQLite."""
        return await admins_repository.get_admin_ids(self._conn)

    @handle_database_errors
    async def add_admin(self, user_id: int) -> bool:
        """Добавляет обычного администратора."""
        if user_id == config.SUPERVISOR_ID:
            return False

        return await admins_repository.add_admin(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def remove_admin(self, user_id: int) -> bool:
        """Удаляет обычного администратора."""
        if user_id == config.SUPERVISOR_ID:
            return False

        return await admins_repository.remove_admin(
            self._conn,
            user_id,
        )

    # --------------------------------------------------
    # Блокировка пользователей
    # --------------------------------------------------

    @handle_database_errors
    async def get_blocked_ids(self) -> set[int]:
        """Возвращает ID заблокированных пользователей."""
        return await blocked_users_repository.get_blocked_ids(self._conn)

    @handle_database_errors
    async def block_user(self, user_id: int) -> bool:
        """Блокирует пользователя, кроме Supervisor."""
        if user_id == config.SUPERVISOR_ID:
            return False
        return await blocked_users_repository.block_user(self._conn, user_id)

    @handle_database_errors
    async def unblock_user(self, user_id: int) -> bool:
        """Снимает блокировку с пользователя."""
        return await blocked_users_repository.unblock_user(self._conn, user_id)


db = Database()

__all__ = [
    "MAX_HISTORY_IMAGES",
    "MAX_HISTORY_MEDIA_MESSAGES",
    "Database",
    "db",
    "handle_database_errors",
    "read_image_as_base64",
]
