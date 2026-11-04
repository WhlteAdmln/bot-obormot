import asyncio

import aiosqlite
import pytest

from bot.errors import DatabaseError
from bot.services.database.decorators import handle_database_errors


class DummyDatabase:
    def __init__(self):
        self._lock = asyncio.Lock()


@pytest.mark.asyncio
async def test_database_error_decorator_translates_sqlite_errors():
    @handle_database_errors
    async def operation(self):
        raise aiosqlite.OperationalError("database is locked")

    database = DummyDatabase()

    with pytest.raises(
        DatabaseError, match="Database operation failed: operation"
    ) as exc:
        await operation(database)

    assert isinstance(exc.value.__cause__, aiosqlite.OperationalError)
    assert not database._lock.locked()


@pytest.mark.asyncio
async def test_database_error_decorator_preserves_database_error():
    original = DatabaseError("specific database failure")

    @handle_database_errors
    async def operation(self):
        raise original

    database = DummyDatabase()

    with pytest.raises(DatabaseError) as exc:
        await operation(database)

    assert exc.value is original
    assert not database._lock.locked()


def test_database_error_decorator_preserves_function_metadata():
    @handle_database_errors
    async def operation(self):
        """operation documentation"""

    assert operation.__name__ == "operation"
    assert operation.__doc__ == "operation documentation"


@pytest.mark.asyncio
async def test_failed_write_rolls_back_and_next_exchange_succeeds(test_db):
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
