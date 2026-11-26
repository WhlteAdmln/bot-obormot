# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories messages."""

import aiosqlite
import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    messages,
)
from tests.support.database_repositories import USER_ID


@pytest.fixture(name="connection")
def fixture_connection(test_db: Database) -> aiosqlite.Connection:
    """Return the open connection of the test database."""
    if test_db.connection is None:
        message = "the test database has no open connection"
        raise RuntimeError(message)
    return test_db.connection


@pytest.mark.asyncio
async def test_messages_repository_adds_and_fetches_complete_exchanges(
    connection: aiosqlite.Connection,
) -> None:
    await messages.add_message(connection, USER_ID, "user", "Вопрос")
    await messages.add_message(connection, USER_ID, "assistant", "Ответ")
    await messages.add_message(connection, USER_ID, "user", "Без ответа")

    rows = await messages.fetch_history_rows(
        connection,
        USER_ID,
        exchange_limit=10,
        max_images=3,
    )

    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "Вопрос"),
        ("assistant", "Ответ"),
    ], "the history differs from the complete exchanges"
