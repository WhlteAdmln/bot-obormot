# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for Telegram update correlation IDs."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO

import pytest
from aiogram.types import TelegramObject, Update

from bot_obormot.app.logging_setup import configure_logging
from bot_obormot.log_context import CorrelationIdFilter, correlation_id
from bot_obormot.middlewares.aliases import MiddlewareData
from bot_obormot.middlewares.correlation_id import CorrelationIdMiddleware
from tests.support.settings import make_settings


@contextmanager
def _correlation_scope(value: str) -> Iterator[None]:
    token = correlation_id.set(value)
    try:
        yield
    finally:
        correlation_id.reset(token)


def _make_record() -> logging.LogRecord:
    """Create a log record for correlation ID tests."""
    return logging.LogRecord(
        "test.correlation",
        logging.INFO,
        __file__,
        1,
        "test message",
        (),
        None,
    )


@pytest.mark.asyncio
async def test_middleware_sets_update_id_on_all_records_and_restores_context() -> None:
    """Each update gets its own ID and the previous context is restored."""
    observed_ids: list[str | None] = []
    log_filter = CorrelationIdFilter()

    async def handler(
        _event: TelegramObject,
        _data: MiddlewareData,
    ) -> str:
        for _ in range(2):
            record = _make_record()
            log_filter.filter(record)
            observed_ids.append(getattr(record, "correlation_id", None))
        return "handled"

    with _correlation_scope("parent"):
        middleware = CorrelationIdMiddleware()
        for update_id in (42, 43):
            result = await middleware(handler, Update(update_id=update_id), {})
            expected_result = "handled"
            assert result == expected_result
            expected_get = "parent"
            assert correlation_id.get() == expected_get

        assert observed_ids == ["42", "42", "43", "43"]


@pytest.mark.asyncio
async def test_middleware_resets_context_when_handler_raises() -> None:
    """The update ID is reset even when the handler raises an exception."""

    async def fail_handler(
        _event: TelegramObject,
        _data: MiddlewareData,
    ) -> object:
        msg = "handler failed"
        raise RuntimeError(msg)

    with _correlation_scope("-"):
        with pytest.raises(RuntimeError, match="handler failed"):
            await CorrelationIdMiddleware()(
                fail_handler,
                Update(update_id=99),
                {},
            )

        expected_get = "-"
        assert correlation_id.get() == expected_get


def test_logging_setup_formats_and_populates_correlation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured handlers include the current ID and a default outside updates."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [handler])
    monkeypatch.setattr(root_logger, "level", root_logger.level)

    monkeypatch.setattr(logging, "basicConfig", lambda **_kwargs: None)
    configure_logging(make_settings())

    assert any(isinstance(item, CorrelationIdFilter) for item in handler.filters)

    token = correlation_id.set("123")
    try:
        handler.handle(_make_record())
    finally:
        correlation_id.reset(token)
    handler.handle(_make_record())

    output = stream.getvalue()
    expected_fragment = " INFO [123] test.correlation: test message"
    assert expected_fragment in output
    expected_fragment = " INFO [-] test.correlation: test message"
    assert expected_fragment in output
