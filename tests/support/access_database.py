# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fake database for access checks."""


class FakeAccessDatabase:
    """Serve administrator and blocked user IDs and record every lookup."""

    def __init__(
        self,
        admin_ids: set[int] | None = None,
        blocked_ids: set[int] | None = None,
        error: Exception | None = None,
    ) -> None:
        """Create a database with the given roles; ``error`` fails every lookup."""
        self.admin_ids = set(admin_ids or ())
        self.blocked_ids = set(blocked_ids or ())
        self.error = error
        self.lookups: list[str] = []

    async def get_blocked_ids(self) -> set[int]:
        """Return the blocked user IDs."""
        return self._lookup("get_blocked_ids", self.blocked_ids)

    async def get_admin_ids(self) -> set[int]:
        """Return the administrator IDs."""
        return self._lookup("get_admin_ids", self.admin_ids)

    def _lookup(self, name: str, ids: set[int]) -> set[int]:
        self.lookups.append(name)
        if self.error is not None:
            raise self.error
        return set(ids)
