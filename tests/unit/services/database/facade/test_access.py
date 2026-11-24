# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the access operations of the database facade."""

import pytest

from bot_obormot.services.database import Database

USER_ID = 111111111

USER_A = 111111111

USER_B = 222222222

SUPERVISOR_ID = 999999999


@pytest.mark.asyncio
async def test_adds_and_removes_admins_without_duplicates(test_db: Database) -> None:
    db = test_db

    assert await db.get_admin_ids() == set()

    assert await db.add_admin(USER_A) is True

    assert await db.add_admin(USER_A) is False

    assert await db.get_admin_ids() == {USER_A}

    assert await db.add_admin(USER_B) is True

    assert await db.get_admin_ids() == {USER_A, USER_B}

    assert await db.remove_admin(USER_A) is True

    assert await db.get_admin_ids() == {USER_B}

    assert await db.remove_admin(USER_A) is False

    assert await db.add_admin(SUPERVISOR_ID) is False
    assert await db.remove_admin(SUPERVISOR_ID) is False


@pytest.mark.asyncio
async def test_blocks_and_unblocks_users_but_never_the_supervisor(
    test_db: Database,
) -> None:
    user_id = USER_ID + 100
    supervisor_id = 999999999

    assert await test_db.get_blocked_ids() == set()
    assert await test_db.block_user(user_id) is True
    assert await test_db.block_user(user_id) is False
    assert await test_db.get_blocked_ids() == {user_id}

    assert await test_db.block_user(supervisor_id) is False
    assert supervisor_id not in await test_db.get_blocked_ids()

    assert await test_db.unblock_user(user_id) is True
    assert await test_db.unblock_user(user_id) is False
    assert await test_db.get_blocked_ids() == set()
