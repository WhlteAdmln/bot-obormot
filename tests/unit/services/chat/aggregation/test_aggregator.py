# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for aggregation aggregator."""

import asyncio
from types import SimpleNamespace

import pytest

from bot_obormot.services.chat.aggregation import aggregator as aggregator_module
from bot_obormot.services.chat.aggregation.aggregator import (
    AggregatedText,
    MessageAggregator,
)
from tests.support.chat_streaming import (
    FakeReplyMessage,
)


def _message(text: str | None, user_id: int | None = 1) -> SimpleNamespace:
    user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(text=text, from_user=user)


@pytest.mark.asyncio
async def test_aggregated_text_remembers_the_last_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Link the combined request to the last message that was added."""
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.1)
    aggregator = MessageAggregator()
    first = FakeReplyMessage("p" * 4000, message_id=1)

    task = asyncio.create_task(aggregator.collect(first))
    await asyncio.sleep(0.01)
    assert await aggregator.collect(FakeReplyMessage("q", message_id=2)) is None
    assert await aggregator.collect(FakeReplyMessage("r", message_id=3)) is None

    result = await task

    assert isinstance(result, AggregatedText)
    assert result.endswith("q\nr")
    assert result.last_message is not None
    assert result.last_message.message_id == 3


@pytest.mark.asyncio
async def test_aggregator_returns_short_standalone_message_immediately() -> None:
    """Aggregator returns short standalone message immediately."""
    aggregator = MessageAggregator()

    assert await aggregator.collect(_message("коротко")) == "коротко"
    assert aggregator._states == {}


@pytest.mark.asyncio
async def test_aggregator_combines_continuation_parts_and_cleans_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aggregator combines continuation parts and cleans state."""
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 2)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.03)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message("первая", 101)))
    await asyncio.sleep(0)
    assert 101 in aggregator._states

    assert await aggregator.collect(_message("вторая", 101)) is None
    assert await asyncio.wait_for(first, timeout=0.5) == "первая\nвторая"
    assert 101 not in aggregator._states


@pytest.mark.asyncio
async def test_aggregator_caps_accumulated_text_and_tracks_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aggregator caps accumulated text and tracks background task."""
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 1)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.5)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message("x" * 4000, 404)))
    await asyncio.sleep(0)

    assert len(aggregator._tasks) == 1
    background_task = next(iter(aggregator._tasks))
    assert background_task.get_name() == "message_aggregation_404"

    for _ in range(4):
        assert await aggregator.collect(_message("y" * 4000, 404)) is None

    result = await asyncio.wait_for(first, timeout=1.0)
    assert len(result) <= aggregator_module.MAX_INPUT_TEXT_LENGTH + 4096
    assert len(result) > aggregator_module.MAX_INPUT_TEXT_LENGTH

    await asyncio.sleep(0)
    assert aggregator._tasks == set()
    assert 404 not in aggregator._states


@pytest.mark.asyncio
async def test_aggregator_ignores_messages_without_text_or_user() -> None:
    """Aggregator ignores messages without text or user."""
    aggregator = MessageAggregator()

    assert await aggregator.collect(_message(None, 1)) is None
    assert await aggregator.collect(_message("текст", None)) == "текст"
