# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database decorators."""

import asyncio

import aiosqlite
import pytest

from bot.errors import DatabaseError
from bot.services.database import Database
from bot.services.database.decorators import handle_database_errors


class DummyDatabase:
    """Dummy database."""

    def __init__(self) -> None:
        """Initializes the test double."""
        self._lock = asyncio.Lock()


@pytest.mark.asyncio
async def test_database_error_decorator_translates_sqlite_errors() -> None:
    """Database error decorator translates sqlite errors."""

    @handle_database_errors
    async def operation(_self: object) -> None:
        msg = "database is locked"
        raise aiosqlite.OperationalError(msg)

    database = DummyDatabase()

    with pytest.raises(
        DatabaseError, match="Database operation failed: operation"
    ) as exc:
        await operation(database)

    assert isinstance(exc.value.__cause__, aiosqlite.OperationalError)
    assert not database._lock.locked()


@pytest.mark.asyncio
async def test_database_error_decorator_preserves_database_error() -> None:
    """Database error decorator preserves database error."""
    original = DatabaseError("specific database failure")

    @handle_database_errors
    async def operation(_self: object) -> None:
        raise original

    database = DummyDatabase()

    with pytest.raises(DatabaseError) as exc:
        await operation(database)

    assert exc.value is original
    assert not database._lock.locked()


def test_database_error_decorator_preserves_function_metadata() -> None:
    """Database error decorator preserves function metadata."""

    @handle_database_errors
    async def operation(self: object) -> None:
        """Operation documentation."""

    assert operation.__name__ == "operation"
    assert operation.__doc__ == "Operation documentation."


@pytest.mark.asyncio
async def test_failed_write_rolls_back_and_next_exchange_succeeds(
    test_db: Database,
) -> None:
    """Ошибка CHECK не должна оставлять транзакцию для следующей записи."""
    with pytest.raises(DatabaseError, match="Database operation failed: add_message"):
        await test_db.add_message(1, "bad-role", "x")

    assert not test_db.connection.in_transaction

    await test_db.add_exchange(1, "q", "a")

    cursor = await test_db.connection.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id",
        (1,),
    )
    rows = await cursor.fetchall()

    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "q"),
        ("assistant", "a"),
    ]
