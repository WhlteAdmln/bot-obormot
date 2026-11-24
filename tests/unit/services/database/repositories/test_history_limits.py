# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories history limits."""

import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    history_limits,
)
from tests.support.database_repositories import USER_ID


@pytest.mark.asyncio
async def test_sets_reads_and_deletes_history_limit(test_db: Database) -> None:
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) is None

    await history_limits.set_history_limit(test_db.connection, USER_ID, 17)
    expected_number = 17
    assert (
        await history_limits.get_history_limit(test_db.connection, USER_ID)
        == expected_number
    )

    await history_limits.delete_history_limit(test_db.connection, USER_ID)
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) is None
