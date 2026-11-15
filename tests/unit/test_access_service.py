# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for access service."""

import pytest

from bot.services.access import user_has_access
from bot.services.access.roles import (
    is_allowlisted,
    is_database_admin,
    is_supervisor,
)


class FakeDatabase:
    """Fake database."""

    def __init__(
        self, admin_ids: object | None = None, blocked_ids: object | None = None
    ) -> None:
        """Initializes the test double."""
        self.admin_ids = set(admin_ids or ())
        self.blocked_ids = set(blocked_ids or ())
        self.calls = 0

    async def get_blocked_ids(self) -> set[int]:
        """Get blocked ids."""
        self.calls += 1
        return self.blocked_ids

    async def get_admin_ids(self) -> set[int]:
        """Get admin ids."""
        self.calls += 1
        return self.admin_ids


def test_role_helpers() -> None:
    """Role helpers."""
    assert is_supervisor(10, 10)
    assert not is_supervisor(10, 11)
    assert is_database_admin(10, {10, 20})
    assert not is_database_admin(10, {20})
    assert is_allowlisted(10, {10, 20})
    assert not is_allowlisted(10, {20})


@pytest.mark.asyncio
async def test_supervisor_does_not_query_database() -> None:
    """Supervisor does not query database."""
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
async def test_database_admin_has_access_even_when_not_allowlisted() -> None:
    """Database admin has access even when not allowlisted."""
    database = FakeDatabase({10})

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users={20},
        database=database,
    )

    assert allowed is True
    assert database.calls == 2


@pytest.mark.asyncio
async def test_empty_allowlist_denies_access_after_admin_lookup() -> None:
    """Empty allowlist denies access after admin lookup."""
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users=set(),
        database=database,
    )

    assert allowed is False
    assert database.calls == 2


@pytest.mark.asyncio
async def test_allow_all_flag_opens_access_after_admin_lookup() -> None:
    """Allow all flag opens access after admin lookup."""
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users=set(),
        database=database,
        allow_all=True,
    )

    assert allowed is True
    assert database.calls == 2


@pytest.mark.asyncio
async def test_allowlisted_user_has_access() -> None:
    """Allowlisted user has access."""
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users={10, 20},
        database=database,
    )

    assert allowed is True
    assert database.calls == 2


@pytest.mark.asyncio
async def test_unknown_user_is_denied() -> None:
    """Unknown user is denied."""
    database = FakeDatabase()

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users={20},
        database=database,
    )

    assert allowed is False
    assert database.calls == 2


@pytest.mark.asyncio
async def test_blocked_user_is_denied_even_when_allowlisted_or_open() -> None:
    """Blocked user is denied even when allowlisted or open."""
    database = FakeDatabase(blocked_ids={10})

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users={10},
        database=database,
        allow_all=True,
    )

    assert allowed is False
    assert database.calls == 1  # Проверка блокировки останавливает доступ до ролей.


@pytest.mark.asyncio
async def test_blocked_database_admin_is_denied() -> None:
    """Blocked database admin is denied."""
    database = FakeDatabase(admin_ids={10}, blocked_ids={10})

    allowed = await user_has_access(
        10,
        supervisor_id=99,
        allowed_users=set(),
        database=database,
    )

    assert allowed is False
    assert database.calls == 1
