# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Публичный API сервиса SQLite.

Реализация фасада находится в :mod:`bot.services.database.facade`.
Публичные имена реэкспортируются здесь, чтобы существующие импорты
``from bot.services.database import db`` и ``Database`` продолжали работать.
"""

from bot.services.database.facade import (
    MAX_HISTORY_IMAGES,
    MAX_HISTORY_MEDIA_MESSAGES,
    Database,
    db,
    handle_database_errors,
    read_image_as_base64,
)

__all__ = [
    "MAX_HISTORY_IMAGES",
    "MAX_HISTORY_MEDIA_MESSAGES",
    "Database",
    "db",
    "handle_database_errors",
    "read_image_as_base64",
]
