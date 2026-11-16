# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for Telegram update correlation IDs."""

import logging
from io import StringIO

import pytest
from aiogram.types import TelegramObject, Update

from bot.app.logging_setup import configure_logging
from bot.log_context import CorrelationIdFilter, correlation_id
from bot.middlewares.aliases import MiddlewareData
from bot.middlewares.correlation_id import CorrelationIdMiddleware
from tests.support.settings import make_settings


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
    previous_token = correlation_id.set("parent")
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

    try:
        middleware = CorrelationIdMiddleware()
        for update_id in (42, 43):
            result = await middleware(handler, Update(update_id=update_id), {})
            assert result == "handled"
            assert correlation_id.get() == "parent"

        assert observed_ids == ["42", "42", "43", "43"]
    finally:
        correlation_id.reset(previous_token)


@pytest.mark.asyncio
async def test_middleware_resets_context_when_handler_raises() -> None:
    """The update ID is reset even when the handler raises an exception."""

    async def fail_handler(
        _event: TelegramObject,
        _data: MiddlewareData,
    ) -> object:
        msg = "handler failed"
        raise RuntimeError(msg)

    previous_token = correlation_id.set("-")
    try:
        with pytest.raises(RuntimeError, match="handler failed"):
            await CorrelationIdMiddleware()(
                fail_handler,
                Update(update_id=99),
                {},
            )

        assert correlation_id.get() == "-"
    finally:
        correlation_id.reset(previous_token)


def test_logging_setup_formats_and_populates_correlation_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured handlers include the current ID and a default outside updates."""
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [handler])

    def fake_basic_config(**kwargs: object) -> None:
        format_string = kwargs["format"]
        assert isinstance(format_string, str)
        handler.setFormatter(logging.Formatter(format_string))

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)
    configure_logging(make_settings())

    assert any(isinstance(item, CorrelationIdFilter) for item in handler.filters)

    token = correlation_id.set("123")
    try:
        handler.handle(_make_record())
    finally:
        correlation_id.reset(token)
    handler.handle(_make_record())

    output = stream.getvalue()
    assert " | 123 | test message" in output
    assert " | - | test message" in output
