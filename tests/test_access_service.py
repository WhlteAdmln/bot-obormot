from types import SimpleNamespace

import pytest

from bot.services.access import user_has_access
from bot.services.access.roles import (
    is_allowlisted,
    is_database_admin,
    is_supervisor,
)


class FakeDatabase:
    def __init__(self, admin_ids=None):
        self.admin_ids = set(admin_ids or ())
        self.calls = 0

    async def get_admin_ids(self):
        self.calls += 1
        return self.admin_ids


def test_role_helpers():
    assert is_supervisor(10, 10)
    assert not is_supervisor(10, 11)
    assert is_database_admin(10, {10, 20})
    assert not is_database_admin(10, {20})
    assert is_allowlisted(10, {10, 20})
    assert not is_allowlisted(10, {20})


@pytest.mark.asyncio
async def test_supervisor_does_not_query_database():
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=10,
        allowed_users={20},
        database=database,
    )

    assert allowed is True
    assert database.calls == 0


@pytest.mark.asyncio
async def test_database_admin_has_access_even_when_not_allowlisted():
    database = FakeDatabase({10})

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users={20},
        database=database,
    )

    assert allowed is True
    assert database.calls == 1


@pytest.mark.asyncio
async def test_empty_allowlist_keeps_access_open_after_admin_lookup():
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users=set(),
        database=database,
    )

    assert allowed is True
    assert database.calls == 1


@pytest.mark.asyncio
async def test_allowlisted_user_has_access():
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users={10, 20},
        database=database,
    )

    assert allowed is True
    assert database.calls == 1


@pytest.mark.asyncio
async def test_unknown_user_is_denied():
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users={20},
        database=database,
    )

    assert allowed is False
    assert database.calls == 1
