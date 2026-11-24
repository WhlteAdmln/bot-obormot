# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Database facade that serializes access to the shared SQLite connection."""

from bot_obormot.services.database.facade.access import AccessOperations
from bot_obormot.services.database.facade.history import (
    MAX_HISTORY_MEDIA_MESSAGES,
    HistoryOperations,
)
from bot_obormot.services.database.facade.user_settings import (
    UserSettingsOperations,
)


class Database(HistoryOperations, UserSettingsOperations, AccessOperations):
    """Facade over the SQLite repositories and use cases."""


__all__ = ["MAX_HISTORY_MEDIA_MESSAGES", "Database"]
