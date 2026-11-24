# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for Telegram update correlation IDs."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from aiogram.types import TelegramObject, Update

from bot_obormot.log_context import CorrelationIdFilter, correlation_id
from bot_obormot.middlewares.aliases import MiddlewareData
from bot_obormot.middlewares.correlation_id import CorrelationIdMiddleware
from tests.support.middleware_handler import RecordingHandler


@contextmanager
def _correlation_scope(value: str) -> Iterator[None]:
    token = correlation_id.set(value)
    try:
        yield
    finally:
        correlation_id.reset(token)


async def _observed_id(event: object) -> str:
    observed: list[str] = []

    async def handler(_event: TelegramObject, _data: MiddlewareData) -> None:
        observed.append(correlation_id.get())

    await CorrelationIdMiddleware()(handler, event, {})
    return observed[0]


async def _record_ids(update_ids: list[int]) -> list[object]:
    log_filter = CorrelationIdFilter()
    observed: list[object] = []

    async def handler(_event: TelegramObject, _data: MiddlewareData) -> None:
        record = logging.LogRecord("bot.test", logging.INFO, __file__, 1, "x", (), None)
        log_filter.filter(record)
        observed.append(getattr(record, "correlation_id", None))

    middleware = CorrelationIdMiddleware()
    for update_id in update_ids:
        await middleware(handler, Update(update_id=update_id), {})
    return observed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "update_id", [42, 0, 2**53 + 1], ids=["usual", "zero", "large"]
)
async def test_binds_the_update_id_while_the_handler_runs(update_id: int) -> None:
    observed = await _observed_id(Update(update_id=update_id))
    assert observed == str(update_id), "the handler saw the wrong correlation ID"


@pytest.mark.asyncio
@pytest.mark.parametrize("event", [object(), "not an update"], ids=["object", "text"])
async def test_binds_a_dash_to_an_event_without_update_id(event: object) -> None:
    observed = await _observed_id(event)
    expected = "-"
    assert observed == expected, "an event without an ID got a correlation ID"


@pytest.mark.asyncio
async def test_tags_log_records_of_consecutive_updates() -> None:
    observed = await _record_ids([7001, 7002])
    expected = ["7001", "7002"]
    assert observed == expected, "log records carry the wrong update ID"


@pytest.mark.asyncio
async def test_returns_the_handler_result() -> None:
    result = await CorrelationIdMiddleware()(
        RecordingHandler("reply sent"), Update(update_id=5), {}
    )
    expected = "reply sent"
    assert result == expected, "the handler result was lost"


@pytest.mark.asyncio
async def test_restores_the_outer_context_after_the_handler() -> None:
    with _correlation_scope("outer"):
        await CorrelationIdMiddleware()(RecordingHandler(), Update(update_id=8), {})
        restored = correlation_id.get()
    expected = "outer"
    assert restored == expected, "the outer correlation ID was not restored"


@pytest.mark.asyncio
async def test_restores_the_outer_context_when_the_handler_raises() -> None:
    handler = RecordingHandler(error=RuntimeError("handler failed"))
    with _correlation_scope("outer"):
        with pytest.raises(RuntimeError, match="handler failed"):
            await CorrelationIdMiddleware()(handler, Update(update_id=99), {})
        restored = correlation_id.get()
    expected = "outer"
    assert restored == expected, "a failing handler leaked its correlation ID"
