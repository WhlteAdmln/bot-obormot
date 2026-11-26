# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the access operations of the database facade."""

import pytest

from bot_obormot.services.database import Database


@pytest.mark.asyncio
async def test_get_admin_ids_is_empty_for_a_new_database(test_db: Database) -> None:
    expected_empty: set[int] = set()
    admin_ids = await test_db.get_admin_ids()
    assert admin_ids == expected_empty, "a new database already has administrators"


@pytest.mark.asyncio
async def test_add_admin_reports_a_new_admin(test_db: Database) -> None:
    user_id = 314159265
    added = await test_db.add_admin(user_id)
    assert added is True, "a new administrator was not reported as added"


@pytest.mark.asyncio
async def test_add_admin_rejects_a_duplicate(test_db: Database) -> None:
    user_id = 271828
    await test_db.add_admin(user_id)
    added_again = await test_db.add_admin(user_id)
    assert added_again is False, "a duplicate administrator was reported as added"


@pytest.mark.asyncio
async def test_add_admin_stores_each_admin_once(test_db: Database) -> None:
    first_id = 111111111
    second_id = -1001234567890
    for user_id in (first_id, first_id, second_id):
        await test_db.add_admin(user_id)
    expected_ids = {first_id, second_id}
    admin_ids = await test_db.get_admin_ids()
    assert admin_ids == expected_ids, "the stored administrators differ"


@pytest.mark.asyncio
async def test_remove_admin_reports_a_removed_admin(test_db: Database) -> None:
    user_id = 7
    await test_db.add_admin(user_id)
    removed = await test_db.remove_admin(user_id)
    assert removed is True, "a removed administrator was not reported as removed"


@pytest.mark.asyncio
async def test_remove_admin_keeps_the_other_admins(test_db: Database) -> None:
    removed_id = 222222222
    kept_id = 2**40 + 3
    await test_db.add_admin(removed_id)
    await test_db.add_admin(kept_id)
    await test_db.remove_admin(removed_id)
    expected_ids = {kept_id}
    admin_ids = await test_db.get_admin_ids()
    assert admin_ids == expected_ids, "removing one administrator changed the others"


@pytest.mark.asyncio
async def test_remove_admin_reports_an_already_removed_admin(
    test_db: Database,
) -> None:
    user_id = 48151623
    await test_db.add_admin(user_id)
    await test_db.remove_admin(user_id)
    removed_again = await test_db.remove_admin(user_id)
    assert removed_again is False, "a missing administrator was reported as removed"


@pytest.mark.asyncio
async def test_add_admin_refuses_the_supervisor(test_db: Database) -> None:
    supervisor_id = 999999999
    added = await test_db.add_admin(supervisor_id)
    assert added is False, "the supervisor was added as an administrator"


@pytest.mark.asyncio
async def test_remove_admin_refuses_the_supervisor(test_db: Database) -> None:
    supervisor_id = 999999999
    removed = await test_db.remove_admin(supervisor_id)
    assert removed is False, "the supervisor was removed as an administrator"


@pytest.mark.asyncio
async def test_get_blocked_ids_is_empty_for_a_new_database(test_db: Database) -> None:
    expected_empty: set[int] = set()
    blocked_ids = await test_db.get_blocked_ids()
    assert blocked_ids == expected_empty, "a new database already blocks users"


@pytest.mark.asyncio
async def test_block_user_reports_a_new_block(test_db: Database) -> None:
    user_id = 111111211
    blocked = await test_db.block_user(user_id)
    assert blocked is True, "a new block was not reported"


@pytest.mark.asyncio
async def test_block_user_rejects_a_duplicate(test_db: Database) -> None:
    user_id = 1618033
    await test_db.block_user(user_id)
    blocked_again = await test_db.block_user(user_id)
    assert blocked_again is False, "a duplicate block was reported as new"


@pytest.mark.asyncio
async def test_block_user_stores_the_blocked_user(test_db: Database) -> None:
    user_id = -42
    await test_db.block_user(user_id)
    expected_ids = {user_id}
    blocked_ids = await test_db.get_blocked_ids()
    assert blocked_ids == expected_ids, "the blocked user was not stored"


@pytest.mark.asyncio
async def test_block_user_refuses_the_supervisor(test_db: Database) -> None:
    supervisor_id = 999999999
    blocked = await test_db.block_user(supervisor_id)
    assert blocked is False, "the supervisor was reported as blocked"


@pytest.mark.asyncio
async def test_block_user_never_stores_the_supervisor(test_db: Database) -> None:
    supervisor_id = 999999999
    await test_db.block_user(supervisor_id)
    blocked_ids = await test_db.get_blocked_ids()
    assert supervisor_id not in blocked_ids, "the supervisor was stored as blocked"


@pytest.mark.asyncio
async def test_unblock_user_reports_a_lifted_block(test_db: Database) -> None:
    user_id = 86400
    await test_db.block_user(user_id)
    unblocked = await test_db.unblock_user(user_id)
    assert unblocked is True, "a lifted block was not reported"


@pytest.mark.asyncio
async def test_unblock_user_reports_a_user_without_a_block(
    test_db: Database,
) -> None:
    user_id = 1234567
    await test_db.block_user(user_id)
    await test_db.unblock_user(user_id)
    unblocked_again = await test_db.unblock_user(user_id)
    assert unblocked_again is False, "a missing block was reported as lifted"


@pytest.mark.asyncio
async def test_unblock_user_removes_the_stored_block(test_db: Database) -> None:
    user_id = 5050505
    await test_db.block_user(user_id)
    await test_db.unblock_user(user_id)
    expected_empty: set[int] = set()
    blocked_ids = await test_db.get_blocked_ids()
    assert blocked_ids == expected_empty, "the lifted block is still stored"
