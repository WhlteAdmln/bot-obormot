# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Декораторы для операций с базой данных."""

import asyncio
import logging
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Concatenate, ParamSpec, Protocol, TypeVar, cast

import aiosqlite

from bot.errors import DatabaseError

# Прежнее имя логгера сохраняется, чтобы не менять маршрутизацию логов.
logger = logging.getLogger("bot.services.database.facade")

_P = ParamSpec("_P")
_R = TypeVar("_R")


class _LockOwner(Protocol):
    """Object that owns the lock serializing access to the SQLite connection."""

    _lock: asyncio.Lock


_S = TypeVar("_S", bound=_LockOwner)


async def _rollback_quietly(connection: aiosqlite.Connection | None) -> None:
    """Сбрасывает незавершённую транзакцию, не скрывая исходную ошибку."""
    if connection is None:
        return

    try:
        await connection.rollback()
    except aiosqlite.Error:
        logger.exception("Database rollback failed")


def handle_database_errors(
    func: Callable[Concatenate[_S, _P], Coroutine[Any, Any, _R]],
) -> Callable[Concatenate[_S, _P], Coroutine[Any, Any, _R]]:
    """Сериализует операции с SQLite и преобразует ошибки БД."""

    @wraps(func)
    async def wrapper(self: _S, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        async with self._lock:
            try:
                return await func(self, *args, **kwargs)

            except DatabaseError:
                raise

            except aiosqlite.Error as error:
                await _rollback_quietly(getattr(self, "connection", None))
                logger.exception("Database error in %s", func.__name__)

                msg = f"Database operation failed: {func.__name__}"
                raise DatabaseError(msg) from error

            except Exception:
                await _rollback_quietly(getattr(self, "connection", None))
                raise

    return cast(
        "Callable[Concatenate[_S, _P], Coroutine[Any, Any, _R]]",
        wrapper,
    )
