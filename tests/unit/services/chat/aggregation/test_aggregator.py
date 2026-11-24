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


def _tasks_named(name: str) -> list[asyncio.Task[object]]:
    return [task for task in asyncio.all_tasks() if task.get_name() == name]


@pytest.mark.asyncio
async def test_aggregated_text_remembers_the_last_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    expected_message_id = 3
    assert result.last_message.message_id == expected_message_id


@pytest.mark.asyncio
async def test_aggregator_returns_short_standalone_message_immediately() -> None:
    aggregator = MessageAggregator()

    expected_text = "коротко"
    assert await aggregator.collect(_message("коротко")) == expected_text


@pytest.mark.asyncio
async def test_aggregator_combines_continuation_parts_and_cleans_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 2)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.03)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message("первая", 101)))
    await asyncio.sleep(0)

    assert await aggregator.collect(_message("вторая", 101)) is None
    expected_text = "первая\nвторая"
    assert await asyncio.wait_for(first, timeout=0.5) == expected_text
    fresh_text = "третья"
    fresh = await aggregator.collect(_message(fresh_text, 101))
    assert fresh == fresh_text, "a finished aggregation must not absorb new text"


@pytest.mark.asyncio
async def test_aggregator_caps_accumulated_text_and_tracks_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 1)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.5)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message("x" * 4000, 404)))
    await asyncio.sleep(0)

    task_name = "message_aggregation_404"
    assert len(_tasks_named(task_name)) == 1

    for _ in range(4):
        assert await aggregator.collect(_message("y" * 4000, 404)) is None

    result = await asyncio.wait_for(first, timeout=1.0)
    assert len(result) <= aggregator_module.MAX_INPUT_TEXT_LENGTH + 4096
    assert len(result) > aggregator_module.MAX_INPUT_TEXT_LENGTH

    await asyncio.sleep(0)
    expected_empty = []
    assert _tasks_named(task_name) == expected_empty, "the background task must finish"


@pytest.mark.asyncio
async def test_aggregator_ignores_messages_without_text_or_user() -> None:
    aggregator = MessageAggregator()

    assert await aggregator.collect(_message(None, 1)) is None
    expected_text = "текст"
    assert await aggregator.collect(_message("текст", None)) == expected_text
