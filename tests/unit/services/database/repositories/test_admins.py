# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for repositories admins."""

import pytest

from bot_obormot.services.database import Database
from bot_obormot.services.database.repositories import admins

UNUSUAL_IDS = [0, -1002003004005, 2**63 - 1]


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [515151, *UNUSUAL_IDS])
async def test_add_admin_reports_a_new_admin(test_db: Database, user_id: int) -> None:
    added = await admins.add_admin(test_db.connection, user_id)
    assert added is True, "a new administrator was not reported as added"


@pytest.mark.asyncio
async def test_add_admin_reports_an_existing_admin(test_db: Database) -> None:
    user_id = 727272
    await admins.add_admin(test_db.connection, user_id)
    added_again = await admins.add_admin(test_db.connection, user_id)
    assert added_again is False, "a duplicate administrator was reported as added"


@pytest.mark.asyncio
async def test_get_admin_ids_returns_every_admin_once(test_db: Database) -> None:
    user_ids = {838383, 0, -1002003004005, 2**63 - 1}
    for user_id in (*user_ids, 838383):
        await admins.add_admin(test_db.connection, user_id)
    stored = await admins.get_admin_ids(test_db.connection)
    assert stored == user_ids, "the stored administrators differ from the added ones"


@pytest.mark.asyncio
async def test_get_admin_ids_is_empty_for_a_new_database(test_db: Database) -> None:
    stored = await admins.get_admin_ids(test_db.connection)
    expected_empty: set[int] = set()
    assert stored == expected_empty, "a new database already has administrators"


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id", [949494, *UNUSUAL_IDS])
async def test_remove_admin_reports_a_removed_admin(
    test_db: Database, user_id: int
) -> None:
    await admins.add_admin(test_db.connection, user_id)
    removed = await admins.remove_admin(test_db.connection, user_id)
    assert removed is True, "a removed administrator was not reported as removed"


@pytest.mark.asyncio
async def test_remove_admin_reports_an_unknown_user(test_db: Database) -> None:
    unknown_id = 161616
    removed = await admins.remove_admin(test_db.connection, unknown_id)
    assert removed is False, "an unknown user was reported as removed"


@pytest.mark.asyncio
async def test_remove_admin_keeps_other_admins(test_db: Database) -> None:
    kept = 272727
    await admins.add_admin(test_db.connection, kept)
    await admins.add_admin(test_db.connection, 383838)
    await admins.remove_admin(test_db.connection, 383838)
    stored = await admins.get_admin_ids(test_db.connection)
    assert stored == {kept}, "removing one administrator touched another"
