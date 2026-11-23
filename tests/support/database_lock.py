# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""A minimal lock owner for the database error decorator."""

import asyncio

from bot_obormot.services.database.decorators import handle_database_errors


class LockOwningDatabase:
    """Own the connection lock the decorator serializes on."""

    def __init__(self) -> None:
        """Create the unlocked connection lock."""
        self._lock = asyncio.Lock()
        self.marker = "pong"

    @handle_database_errors
    async def ping(self) -> str:
        """Return a marker; it can only run while the lock is free."""
        return self.marker
