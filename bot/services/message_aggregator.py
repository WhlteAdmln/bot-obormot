"""Обратная совместимость для прежнего пути message_aggregator."""

from bot.services.chat.aggregation import (
    MessageAggregator,
    message_aggregator,
    MESSAGE_AGGREGATION_WINDOW,
    MESSAGE_LENGTH_THRESHOLD,
)
from bot.services.chat.aggregation.aggregator import logger, _utf16_length
from bot.services.chat.aggregation.state import _AggregationState

__all__ = [
    "MessageAggregator",
    "message_aggregator",
    "MESSAGE_AGGREGATION_WINDOW",
    "MESSAGE_LENGTH_THRESHOLD",
]
