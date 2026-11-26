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
    async def operation(_self: LockOwningDatabase) -> None:
        msg = "database is locked"
        raise aiosqlite.OperationalError(msg)

    database = LockOwningDatabase()

    with pytest.raises(
        DatabaseError, match="Database operation failed: operation"
    ) as exc:
        await operation(database)

    cause = exc.value.__cause__
    assert isinstance(cause, aiosqlite.OperationalError), "the sqlite cause is lost"


@pytest.mark.asyncio
async def test_decorator_releases_the_lock_after_sqlite_error() -> None:

    @handle_database_errors
    async def operation(_self: LockOwningDatabase) -> None:
        msg = "disk I/O error"
        raise aiosqlite.OperationalError(msg)

    database = LockOwningDatabase()

    with pytest.raises(DatabaseError):
        await operation(database)

    released = await asyncio.wait_for(database.ping(), 1)
    assert released == database.marker, "the lock must be released after a failure"


@pytest.mark.asyncio
async def test_database_error_decorator_preserves_database_error() -> None:
    original = DatabaseError("specific database failure")

    @handle_database_errors
    async def operation(_self: LockOwningDatabase) -> None:
        raise original

    database = LockOwningDatabase()

    with pytest.raises(DatabaseError) as exc:
        await operation(database)

    assert exc.value is original, "the original database error was replaced"


@pytest.mark.asyncio
async def test_decorator_releases_the_lock_after_database_error() -> None:
    original = DatabaseError("constraint check failed")

    @handle_database_errors
    async def operation(_self: LockOwningDatabase) -> None:
        raise original

    database = LockOwningDatabase()

    with pytest.raises(DatabaseError):
        await operation(database)

    released = await asyncio.wait_for(database.ping(), 1)
    assert released == database.marker, "the lock must be released after a failure"


def test_database_error_decorator_preserves_function_name() -> None:

    @handle_database_errors
    async def rename_chat(_self: LockOwningDatabase) -> None:
        """Rename the chat."""

    expected_name = "rename_chat"
    assert rename_chat.__name__ == expected_name, "the function name was lost"


def test_database_error_decorator_preserves_function_docstring() -> None:

    @handle_database_errors
    async def operation(_self: LockOwningDatabase) -> None:
        """Operation documentation."""

    expected_doc = "Operation documentation."
    assert operation.__doc__ == expected_doc, "the docstring was lost"


@pytest.mark.asyncio
async def test_failed_write_rolls_back_the_transaction(test_db: Database) -> None:
    user_id = 4096
    with pytest.raises(DatabaseError, match="Database operation failed: add_message"):
        await test_db.add_message(user_id, "bad-role", "отклонено")

    in_transaction = test_db.connection.in_transaction
    assert in_transaction is False, "a failed write left a transaction open"


@pytest.mark.asyncio
async def test_failed_write_rolls_back_and_next_exchange_succeeds(
    test_db: Database,
) -> None:
    user_id = 1
    question = "Сколько времени?"
    answer = "Без пяти три"
    with pytest.raises(DatabaseError, match="Database operation failed: add_message"):
        await test_db.add_message(user_id, "bad-role", "мусор")

    await test_db.add_exchange(user_id, question, answer)

    cursor = await test_db.connection.execute(
        "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id",
        (user_id,),
    )
    rows = await cursor.fetchall()

    expected = [("user", question), ("assistant", answer)]
    stored = [(row["role"], row["content"]) for row in rows]
    assert stored == expected, "the exchange after a failed write was not stored"
