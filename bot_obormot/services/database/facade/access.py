# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Administrator and block-list operations of the database facade."""

from bot_obormot.services.database.decorators import handle_database_errors
from bot_obormot.services.database.facade.core import DatabaseCore
from bot_obormot.services.database.repositories import (
    admins as admins_repository,
)
from bot_obormot.services.database.repositories import (
    blocked_users as blocked_users_repository,
)


class AccessOperations(DatabaseCore):
    """Regular administrators and blocked users; the supervisor is protected."""

    @handle_database_errors
    async def get_admin_ids(self) -> set[int]:
        """Return the IDs of regular administrators from SQLite."""
        return await admins_repository.get_admin_ids(self._conn)

    @handle_database_errors
    async def add_admin(self, user_id: int) -> bool:
        """Add a regular administrator."""
        if user_id == self.settings.SUPERVISOR_ID:
            return False

        return await admins_repository.add_admin(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def remove_admin(self, user_id: int) -> bool:
        """Remove a regular administrator."""
        if user_id == self.settings.SUPERVISOR_ID:
            return False

        return await admins_repository.remove_admin(
            self._conn,
            user_id,
        )

    @handle_database_errors
    async def get_blocked_ids(self) -> set[int]:
        """Return the IDs of blocked users."""
        return await blocked_users_repository.get_blocked_ids(self._conn)

    @handle_database_errors
    async def block_user(self, user_id: int) -> bool:
        """Block a user, except for the supervisor."""
        if user_id == self.settings.SUPERVISOR_ID:
            return False
        return await blocked_users_repository.block_user(self._conn, user_id)

    @handle_database_errors
    async def unblock_user(self, user_id: int) -> bool:
        """Unblock a user."""
        return await blocked_users_repository.unblock_user(self._conn, user_id)


__all__ = ["AccessOperations"]
