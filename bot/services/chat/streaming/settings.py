# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Настройки отображения потокового ответа в Telegram."""

STREAM_TOKEN_THRESHOLD = 150
STREAM_UPDATE_INTERVAL = 0.8
MAX_MESSAGE_LENGTH = 3900

__all__ = [
    "MAX_MESSAGE_LENGTH",
    "STREAM_TOKEN_THRESHOLD",
    "STREAM_UPDATE_INTERVAL",
]
