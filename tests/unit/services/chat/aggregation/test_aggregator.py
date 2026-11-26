# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for aggregation aggregator."""

import asyncio
from types import SimpleNamespace

import pytest

from bot_obormot.common.validation import MAX_INPUT_TEXT_LENGTH
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


async def _aggregate_long_message(
    monkeypatch: pytest.MonkeyPatch, parts: list[str]
) -> tuple[list[AggregatedText | str | None], AggregatedText | str | None]:
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.1)
    aggregator = MessageAggregator()
    first = FakeReplyMessage("p" * 4000, message_id=1)

    task = asyncio.create_task(aggregator.collect(first))
    await asyncio.sleep(0.01)
    continuations = [
        await aggregator.collect(FakeReplyMessage(part, message_id=index))
        for index, part in enumerate(parts, start=2)
    ]
    return continuations, await task


@pytest.mark.asyncio
async def test_aggregated_text_absorbs_the_continuation_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    continuations, _ = await _aggregate_long_message(monkeypatch, ["q", "r"])

    expected_continuations = [None, None]
    assert continuations == expected_continuations, "a continuation was returned"


@pytest.mark.asyncio
async def test_aggregated_text_is_an_aggregated_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, result = await _aggregate_long_message(monkeypatch, ["хвост"])

    assert isinstance(result, AggregatedText), "the result is not an AggregatedText"


@pytest.mark.asyncio
async def test_aggregated_text_ends_with_the_continuations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, result = await _aggregate_long_message(monkeypatch, ["q", "r"])

    expected_tail = "q\nr"
    assert str(result).endswith(expected_tail), "the continuations are missing"


@pytest.mark.asyncio
async def test_aggregated_text_remembers_the_last_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, result = await _aggregate_long_message(monkeypatch, ["s", "t", "u"])

    expected_message_id = 4
    last_message = getattr(result, "last_message", None)
    message_id = getattr(last_message, "message_id", None)
    assert message_id == expected_message_id, "the last message was not remembered"


@pytest.mark.asyncio
async def test_aggregator_returns_short_standalone_message_immediately() -> None:
    aggregator = MessageAggregator()

    expected_text = "коротко"
    result = await aggregator.collect(_message(expected_text))
    assert result == expected_text, "a short message was not returned at once"


async def _combine_two_parts(
    monkeypatch: pytest.MonkeyPatch, first_text: str, second_text: str, user_id: int
) -> tuple[MessageAggregator, str | None, str | None]:
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 2)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.03)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message(first_text, user_id)))
    await asyncio.sleep(0)
    second = await aggregator.collect(_message(second_text, user_id))
    combined = await asyncio.wait_for(first, timeout=0.5)
    return aggregator, second, combined


@pytest.mark.asyncio
async def test_aggregator_absorbs_a_continuation_part(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, second, _ = await _combine_two_parts(monkeypatch, "начало", "конец", 57)

    assert second is None, "a continuation part was returned on its own"


@pytest.mark.asyncio
async def test_aggregator_combines_continuation_parts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, combined = await _combine_two_parts(monkeypatch, "первая", "вторая", 101)

    expected_text = "первая\nвторая"
    assert combined == expected_text, "the parts were not joined by a line break"


@pytest.mark.asyncio
async def test_aggregator_cleans_state_after_combining(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregator, _, _ = await _combine_two_parts(monkeypatch, "раз", "два", 2024)

    fresh_text = "третья"
    fresh = await aggregator.collect(_message(fresh_text, 2024))
    assert fresh == fresh_text, "a finished aggregation must not absorb new text"


async def _start_capped_aggregation(
    monkeypatch: pytest.MonkeyPatch, user_id: int, window: float
) -> tuple[MessageAggregator, asyncio.Task[AggregatedText | str | None]]:
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 1)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", window)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message("x" * 4000, user_id)))
    await asyncio.sleep(0)
    return aggregator, first


async def _capped_result(
    monkeypatch: pytest.MonkeyPatch, user_id: int
) -> AggregatedText | str | None:
    aggregator, first = await _start_capped_aggregation(monkeypatch, user_id, 0.1)
    for _ in range(4):
        await aggregator.collect(_message("y" * 4000, user_id))
    return await asyncio.wait_for(first, timeout=1.0)


@pytest.mark.asyncio
async def test_aggregator_tracks_a_named_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, first = await _start_capped_aggregation(monkeypatch, 404, 0.1)

    task_count = len(_tasks_named("message_aggregation_404"))
    await asyncio.wait_for(first, timeout=1.0)
    expected_count = 1
    assert task_count == expected_count, "the background task is not tracked by name"


@pytest.mark.asyncio
async def test_aggregator_absorbs_parts_while_capping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    aggregator, first = await _start_capped_aggregation(monkeypatch, 405, 0.1)

    replies = [await aggregator.collect(_message("y" * 4000, 405)) for _ in range(4)]
    await asyncio.wait_for(first, timeout=1.0)

    expected_replies = [None, None, None, None]
    assert replies == expected_replies, "a continuation part was returned on its own"


@pytest.mark.asyncio
async def test_aggregator_caps_accumulated_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _capped_result(monkeypatch, 406)

    max_length = MAX_INPUT_TEXT_LENGTH + 4096
    assert len(str(result)) <= max_length, "the accumulated text was not capped"


@pytest.mark.asyncio
async def test_aggregator_keeps_text_beyond_the_input_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = await _capped_result(monkeypatch, 407)

    min_length = MAX_INPUT_TEXT_LENGTH
    assert len(str(result)) > min_length, "the accumulated text was cut too short"


@pytest.mark.asyncio
async def test_aggregator_finishes_the_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _capped_result(monkeypatch, 408)

    await asyncio.sleep(0)
    expected_empty: list[asyncio.Task[object]] = []
    remaining = _tasks_named("message_aggregation_408")
    assert remaining == expected_empty, "the background task must finish"


@pytest.mark.asyncio
async def test_aggregator_ignores_messages_without_text() -> None:
    aggregator = MessageAggregator()

    result = await aggregator.collect(_message(None, 31))
    assert result is None, "a message without text was not ignored"


@pytest.mark.asyncio
async def test_aggregator_returns_text_of_messages_without_user() -> None:
    aggregator = MessageAggregator()

    expected_text = "текст"
    result = await aggregator.collect(_message(expected_text, None))
    assert result == expected_text, "a message without user lost its text"
