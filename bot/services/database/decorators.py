"""Декораторы для операций с базой данных."""

import logging
from functools import wraps

import aiosqlite

from bot.errors import DatabaseError

# Прежнее имя логгера сохраняется, чтобы не менять маршрутизацию логов.
logger = logging.getLogger("bot.services.database.facade")


async def _rollback_quietly(connection) -> None:
    """Сбрасывает незавершённую транзакцию, не скрывая исходную ошибку."""
    if connection is None:
        return

    try:
        await connection.rollback()
    except aiosqlite.Error:
        logger.exception("Database rollback failed")


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
                await _rollback_quietly(getattr(self, "connection", None))
                logger.exception("Database error in %s", func.__name__)

                raise DatabaseError(
                    f"Database operation failed: {func.__name__}"
                ) from error

            except Exception:
                await _rollback_quietly(getattr(self, "connection", None))
                raise

    return wrapper
