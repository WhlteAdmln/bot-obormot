# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Public API for the SQLite database service."""

from bot_obormot.services.database.decorators import handle_database_errors
from bot_obormot.services.database.facade import MAX_HISTORY_MEDIA_MESSAGES, Database
from bot_obormot.services.database.files.image_storage import read_image_as_base64

__all__ = [
    "MAX_HISTORY_MEDIA_MESSAGES",
    "Database",
    "handle_database_errors",
    "read_image_as_base64",
]
