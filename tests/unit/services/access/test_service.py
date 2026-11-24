# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for access service."""

import pytest

from bot_obormot.services.access import user_has_access
from tests.support.access_database import FakeAccessDatabase


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "allowed_users", "admin_ids", "allow_all"),
    [
        (901, set(), set(), False),
        (4242, {77}, {4242}, False),
        (4242, {77, 4242}, set(), False),
        (4242, set(), set(), True),
        (2**63 - 1, {2**63 - 1}, set(), False),
    ],
    ids=["supervisor", "database-admin", "allowlisted", "open", "largest-id"],
)
async def test_grants_access(
    user_id: int,
    allowed_users: set[int],
    admin_ids: set[int],
    *,
    allow_all: bool,
) -> None:
    database = FakeAccessDatabase(admin_ids=admin_ids)
    allowed = await user_has_access(
        user_id,
        supervisor_id=901,
        allowed_users=allowed_users,
        database=database,
        allow_all=allow_all,
    )
    assert allowed is True, "a user with a role was denied"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "allowed_users", "admin_ids", "blocked_ids", "allow_all"),
    [
        (4242, {77}, set(), set(), False),
        (4242, set(), set(), set(), False),
        (4242, {4242}, set(), {4242}, True),
        (4242, set(), {4242}, {4242}, False),
        (-901, {901}, {901}, set(), False),
        (0, {77}, set(), set(), False),
    ],
    ids=[
        "outsider",
        "empty-allowlist",
        "blocked-allowlisted-open",
        "blocked-admin",
        "negated-supervisor",
        "zero",
    ],
)
async def test_denies_access(
    user_id: int,
    allowed_users: set[int],
    admin_ids: set[int],
    blocked_ids: set[int],
    *,
    allow_all: bool,
) -> None:
    database = FakeAccessDatabase(admin_ids=admin_ids, blocked_ids=blocked_ids)
    allowed = await user_has_access(
        user_id,
        supervisor_id=901,
        allowed_users=allowed_users,
        database=database,
        allow_all=allow_all,
    )
    assert allowed is False, "a user without a role was let in"


@pytest.mark.asyncio
async def test_grants_supervisor_without_reading_the_database() -> None:
    database = FakeAccessDatabase(blocked_ids={901})
    await user_has_access(
        901, supervisor_id=901, allowed_users=set(), database=database
    )
    expected_empty: list[str] = []
    assert database.lookups == expected_empty, "the supervisor check read the database"


@pytest.mark.asyncio
async def test_stops_at_the_block_list_for_a_blocked_user() -> None:
    database = FakeAccessDatabase(admin_ids={318}, blocked_ids={318})
    await user_has_access(
        318, supervisor_id=901, allowed_users={318}, database=database
    )
    expected = ["get_blocked_ids"]
    assert database.lookups == expected, "a blocked user reached the admin lookup"


@pytest.mark.asyncio
async def test_reads_block_list_before_admin_list() -> None:
    database = FakeAccessDatabase()
    await user_has_access(
        6061, supervisor_id=901, allowed_users={6061}, database=database
    )
    expected = ["get_blocked_ids", "get_admin_ids"]
    assert database.lookups == expected, "the lookups ran in the wrong order"


@pytest.mark.asyncio
async def test_fails_closed_when_the_database_is_unavailable() -> None:
    message = "disk I/O error on admins"
    database = FakeAccessDatabase(error=RuntimeError(message))
    with pytest.raises(RuntimeError) as caught:
        await user_has_access(
            6061,
            supervisor_id=901,
            allowed_users={6061},
            database=database,
            allow_all=True,
        )
    assert str(caught.value) == message, "a database failure did not propagate"
