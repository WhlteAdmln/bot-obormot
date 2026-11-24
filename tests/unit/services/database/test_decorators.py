# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for database decorators."""

import asyncio

import aiosqlite
import pytest

from bot_obormot.errors import DatabaseError
from bot_obormot.services.database import Database
from bot_obormot.services.database.decorators import handle_database_errors
from tests.support.database_lock import LockOwningDatabase


@pytest.mark.asyncio
async def test_database_error_decorator_translates_sqlite_errors() -> None:

    @handle_database_errors
    async def operation(_self: object) -> None:
        msg = "database is locked"
        raise aiosqlite.OperationalError(msg)

    database = LockOwningDatabase()

    with pytest.raises(
        DatabaseError, match="Database operation failed: operation"
    ) as exc:
        await operation(database)

    assert isinstance(exc.value.__cause__, aiosqlite.OperationalError)
    released = await asyncio.wait_for(database.ping(), 1)
    assert released == database.marker, "the lock must be released after a failure"


@pytest.mark.asyncio
async def test_database_error_decorator_preserves_database_error() -> None:
    original = DatabaseError("specific database failure")

    @handle_database_errors
    async def operation(_self: object) -> None:
        raise original

    database = LockOwningDatabase()

    with pytest.raises(DatabaseError) as exc:
        await operation(database)

    assert exc.value is original
    released = await asyncio.wait_for(database.ping(), 1)
    assert released == database.marker, "the lock must be released after a failure"


def test_database_error_decorator_preserves_function_metadata() -> None:

    @handle_database_errors
    async def operation(_self: object) -> None:
        """Operation documentation."""

    expected_name = "operation"
    assert operation.__name__ == expected_name
    expected_doc = "Operation documentation."
    assert operation.__doc__ == expected_doc


@pytest.mark.asyncio
async def test_failed_write_rolls_back_and_next_exchange_succeeds(
    test_db: Database,
) -> None:
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
