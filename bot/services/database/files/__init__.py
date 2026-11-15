# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Файловое хранилище медиа, связанных с историей сообщений."""

from bot.services.database.files.image_storage import (
    delete_image,
    list_image_files,
    read_image_as_base64,
    save_image,
)

__all__ = [
    "delete_image",
    "list_image_files",
    "read_image_as_base64",
    "save_image",
]
