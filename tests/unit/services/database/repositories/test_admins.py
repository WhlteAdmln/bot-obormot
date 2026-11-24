# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories admins."""

import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import (
    admins,
)
from tests.support.database_repositories import USER_ID


@pytest.mark.asyncio
async def test_admins_repository_is_idempotent_and_facade_excludes_supervisor(
    test_db: Database,
) -> None:
    assert await admins.add_admin(test_db.connection, USER_ID) is True
    assert await admins.add_admin(test_db.connection, USER_ID) is False
    assert await test_db.get_admin_ids() == {USER_ID}

    assert await test_db.add_admin(test_db.settings.SUPERVISOR_ID) is False
    assert await test_db.remove_admin(test_db.settings.SUPERVISOR_ID) is False
    assert await test_db.get_admin_ids() == {USER_ID}

    assert await admins.remove_admin(test_db.connection, USER_ID) is True
    assert await admins.remove_admin(test_db.connection, USER_ID) is False
