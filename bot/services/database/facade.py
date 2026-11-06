import asyncio
import logging
import os
from pathlib import Path

import aiosqlite

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
from bot.services.database.usecases.cleanup import (
    cleanup_old_images as cleanup_old_images_usecase,
)
from bot.services.database.usecases.exchange import add_exchange as add_exchange_usecase
from bot.services.database.usecases.history import (
    get_history as get_history_usecase,
)
from bot.services.database.usecases.history import (
    reset_history as reset_history_usecase,
)

logger = logging.getLogger(__name__)

# Максимум медиа-сообщений в истории; все кадры сообщения загружаются вместе.
MAX_HISTORY_MEDIA_MESSAGES = 3
# Старое имя оставлено для совместимости с публичными импортами.
MAX_HISTORY_IMAGES = MAX_HISTORY_MEDIA_MESSAGES


class Database:
    def __init__(self):
        self.connection: aiosqlite.Connection | None = None

        self.images_dir = Path(config.DATABASE_PATH).resolve().parent / "images"

        # Защищает общее SQLite-соединение от конкурентного использования.
        self._lock = asyncio.Lock()

    @handle_database_errors
    async def connect(self):
        """Создаёт подключение, таблицы и выполняет миграции."""

        directory = os.path.dirname(config.DATABASE_PATH)

        if directory:
            os.makedirs(directory, exist_ok=True)

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
    async def close(self):
        """Закрывает соединение с базой данных."""

        if self.connection:
            await self.connection.close()
            self.connection = None

    @handle_database_errors
    async def health_check(self) -> bool:
        """Проверяет доступность SQLite."""

        if self.connection is None:
            raise DatabaseError("Database connection is not initialized")

        cursor = await self.connection.execute("SELECT 1")
        row = await cursor.fetchone()

        return row is not None and row[0] == 1

    @handle_database_errors
    async def add_message(
        self,
        user_id: int,
        role: str,
        content: str,
    ):
        """Добавляет отдельное сообщение в историю."""
        await messages_repository.add_message(
            self.connection,
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
    ):
        """Атомарно сохраняет обмен сообщениями и изображения."""
        await add_exchange_usecase(
            self.connection,
            self._lock,
            self.images_dir,
            user_id,
            user_text,
            assistant_text,
            media,
            logger,
        )

    @handle_database_errors
    async def prune_history(self, user_id: int) -> None:
        """Ограничивает число хранимых сообщений пользователя."""
        paths = await messages_repository.prune_user_history(
            self.connection,
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
    ) -> list[dict]:
        """Загружает последние полные обмены пользователя."""
        return await get_history_usecase(
            self.connection,
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
            self.connection,
            self.images_dir,
            retention_days,
            orphan_grace_hours,
            logger,
            delete_image,
        )

    @handle_database_errors
    async def reset_history(self, user_id: int):
        """Удаляет историю пользователя и связанные изображения."""
        await reset_history_usecase(
            self.connection,
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
            self.connection,
            user_id,
            delete_image,
            logger,
            images_dir=self.images_dir,
        )
        await user_settings_repository.delete_system_prompt(
            self.connection,
            user_id,
        )
        await history_limits_repository.delete_history_limit(
            self.connection,
            user_id,
        )

    @handle_database_errors
    async def get_system_prompt(self, user_id: int) -> str:
        prompt = await user_settings_repository.get_system_prompt(
            self.connection,
            user_id,
        )
        return prompt if prompt is not None else config.DEFAULT_SYSTEM_PROMPT

    @handle_database_errors
    async def get_user_system_prompt(self, user_id: int) -> str | None:
        """Возвращает персональный промпт пользователя или None."""
        return await user_settings_repository.get_system_prompt(
            self.connection,
            user_id,
        )

    @handle_database_errors
    async def delete_system_prompt(self, user_id: int):
        """Удаляет персональный системный промпт пользователя."""
        await user_settings_repository.delete_system_prompt(
            self.connection,
            user_id,
        )

    @handle_database_errors
    async def set_system_prompt(
        self,
        user_id: int,
        prompt: str,
    ):
        """Сохраняет персональный системный промпт пользователя."""
        await user_settings_repository.set_system_prompt(
            self.connection,
            user_id,
            prompt,
        )

    @handle_database_errors
    async def get_history_limit(self, user_id: int) -> int:
        """Возвращает индивидуальный лимит или стандартное значение."""
        exchange_limit = await history_limits_repository.get_history_limit(
            self.connection,
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
    ):
        """Устанавливает индивидуальный лимит истории."""
        if not 1 <= exchange_limit <= config.MAX_HISTORY_EXCHANGES:
            raise ValueError("Недопустимый лимит истории.")

        await history_limits_repository.set_history_limit(
            self.connection,
            user_id,
            exchange_limit,
        )

    @handle_database_errors
    async def delete_history_limit(self, user_id: int):
        """Удаляет индивидуальный лимит истории."""
        await history_limits_repository.delete_history_limit(
            self.connection,
            user_id,
        )

    # --------------------------------------------------
    # Управление администраторами
    # --------------------------------------------------

    @handle_database_errors
    async def get_admin_ids(self) -> set[int]:
        """Возвращает ID обычных администраторов из SQLite."""
        return await admins_repository.get_admin_ids(self.connection)

    @handle_database_errors
    async def add_admin(self, user_id: int) -> bool:
        """Добавляет обычного администратора."""
        if user_id == config.SUPERVISOR_ID:
            return False

        return await admins_repository.add_admin(
            self.connection,
            user_id,
        )

    @handle_database_errors
    async def remove_admin(self, user_id: int) -> bool:
        """Удаляет обычного администратора."""
        if user_id == config.SUPERVISOR_ID:
            return False

        return await admins_repository.remove_admin(
            self.connection,
            user_id,
        )

    # --------------------------------------------------
    # Блокировка пользователей
    # --------------------------------------------------

    @handle_database_errors
    async def get_blocked_ids(self) -> set[int]:
        """Возвращает ID заблокированных пользователей."""
        return await blocked_users_repository.get_blocked_ids(self.connection)

    @handle_database_errors
    async def block_user(self, user_id: int) -> bool:
        """Блокирует пользователя, кроме Supervisor."""
        if user_id == config.SUPERVISOR_ID:
            return False
        return await blocked_users_repository.block_user(self.connection, user_id)

    @handle_database_errors
    async def unblock_user(self, user_id: int) -> bool:
        """Снимает блокировку с пользователя."""
        return await blocked_users_repository.unblock_user(self.connection, user_id)


db = Database()
