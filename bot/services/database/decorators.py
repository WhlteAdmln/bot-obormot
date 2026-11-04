"""Декораторы для операций с базой данных."""

import logging
from functools import wraps

import aiosqlite

from bot.errors import DatabaseError


# Сохраняем исходное имя логгера фасада, чтобы формат и маршрутизация
# существующих лог-записей не менялись после переноса декоратора.
logger = logging.getLogger("bot.services.database.facade")


def handle_database_errors(func):
    """Сериализует операции с SQLite и преобразует ошибки БД."""

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        async with self._lock:
            try:
                return await func(self, *args, **kwargs)

            except DatabaseError:
                raise

            except aiosqlite.Error as error:
                logger.exception(
                    "Database error in %s",
                    func.__name__,
                )

                raise DatabaseError(
                    f"Database operation failed: {func.__name__}"
                ) from error

    return wrapper
