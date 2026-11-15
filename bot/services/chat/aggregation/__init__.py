# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Объединение последовательных текстовых сообщений."""

from bot.services.chat.aggregation.aggregator import MessageAggregator
from bot.services.chat.aggregation.config import (
    MESSAGE_AGGREGATION_WINDOW,
    MESSAGE_LENGTH_THRESHOLD,
)

__all__ = [
    "MESSAGE_AGGREGATION_WINDOW",
    "MESSAGE_LENGTH_THRESHOLD",
    "MessageAggregator",
]
