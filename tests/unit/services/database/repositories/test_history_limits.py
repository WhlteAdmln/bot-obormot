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
async def test_history_limits_repository_crud(test_db: Database) -> None:
    """History limits repository crud."""
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) is None

    await history_limits.set_history_limit(test_db.connection, USER_ID, 17)
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) == 17

    await history_limits.delete_history_limit(test_db.connection, USER_ID)
    assert await history_limits.get_history_limit(test_db.connection, USER_ID) is None
