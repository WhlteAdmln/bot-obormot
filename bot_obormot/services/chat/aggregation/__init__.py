# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Aggregate consecutive text messages."""

from bot_obormot.services.chat.aggregation.aggregator import (
    AggregatedText,
    MessageAggregator,
)
from bot_obormot.services.chat.aggregation.config import (
    MESSAGE_AGGREGATION_WINDOW,
    MESSAGE_LENGTH_THRESHOLD,
)

__all__ = [
    "MESSAGE_AGGREGATION_WINDOW",
    "MESSAGE_LENGTH_THRESHOLD",
    "AggregatedText",
    "MessageAggregator",
]
