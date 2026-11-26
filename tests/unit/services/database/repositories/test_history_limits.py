# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories history limits."""

import aiosqlite
import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    history_limits,
)


@pytest.fixture(name="connection")
def fixture_connection(test_db: Database) -> aiosqlite.Connection:
    """Return the open connection of the test database."""
    if test_db.connection is None:
        message = "the test database has no open connection"
        raise RuntimeError(message)
    return test_db.connection


@pytest.mark.asyncio
async def test_get_history_limit_returns_none_without_a_limit(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 31337
    limit = await history_limits.get_history_limit(connection, user_id)
    assert limit is None, "a user without a limit has a stored limit"


@pytest.mark.asyncio
async def test_set_history_limit_stores_the_limit(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 662607
    expected_number = 17
    await history_limits.set_history_limit(connection, user_id, expected_number)
    limit = await history_limits.get_history_limit(connection, user_id)
    assert limit == expected_number, "the stored limit differs from the one set"


@pytest.mark.asyncio
async def test_delete_history_limit_removes_the_limit(
    connection: aiosqlite.Connection,
) -> None:
    user_id = 1234567890
    number = 3
    await history_limits.set_history_limit(connection, user_id, number)
    await history_limits.delete_history_limit(connection, user_id)
    limit = await history_limits.get_history_limit(connection, user_id)
    assert limit is None, "the deleted limit is still stored"
