"""Объединение последовательных текстовых сообщений."""

from bot.services.chat.aggregation.aggregator import (
    MessageAggregator,
    message_aggregator,
)
from bot.services.chat.aggregation.config import (
    MESSAGE_AGGREGATION_WINDOW,
    MESSAGE_LENGTH_THRESHOLD,
)

__all__ = [
    "MessageAggregator",
    "message_aggregator",
    "MESSAGE_AGGREGATION_WINDOW",
    "MESSAGE_LENGTH_THRESHOLD",
]
