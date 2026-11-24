# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for app logging setup."""

import logging
from io import StringIO

import pytest

from bot_obormot.app.logging_setup import configure_logging
from bot_obormot.log_context import CorrelationIdFilter, correlation_id
from bot_obormot.log_filters import SecretsFilter
from bot_obormot.settings import load_settings
from tests.support.settings import make_settings


def _configured_handler(
    monkeypatch: pytest.MonkeyPatch, **values: str
) -> logging.StreamHandler:
    handler = logging.StreamHandler(StringIO())
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [handler])
    monkeypatch.setattr(root_logger, "level", root_logger.level)
    monkeypatch.setattr(logging, "basicConfig", lambda **_kwargs: None)
    configure_logging(make_settings(**values))
    return handler


def _formatted_line(monkeypatch: pytest.MonkeyPatch, context_id: str | None) -> str:
    handler = _configured_handler(monkeypatch)
    record = logging.LogRecord(
        "test.correlation", logging.INFO, __file__, 1, "test message", (), None
    )
    token = correlation_id.set(context_id) if context_id is not None else None
    try:
        handler.handle(record)
    finally:
        if token is not None:
            correlation_id.reset(token)
    return handler.stream.getvalue()


@pytest.mark.parametrize(
    "key",
    ["AUDIODOC_AUDIO_KEY", "AUDIODOC_DOCUMENT_KEY"],
    ids=["audio", "document"],
)
def test_configure_logging_redacts_audiodoc_keys(
    caplog: pytest.LogCaptureFixture, key: str
) -> None:
    settings = load_settings(
        {
            "SUPERVISOR_ID": "1",
            "AUDIODOC_URL": "https://audio.test",
            "AUDIODOC_AUDIO_KEY": "whisper-secret-key",
            "AUDIODOC_DOCUMENT_KEY": "document-secret-key",
        }
    )
    with caplog.at_level(logging.WARNING):
        configure_logging(settings)
        logging.getLogger("bot_obormot.main").warning(
            "Configured key: %s", getattr(settings, key)
        )
    expected = ["Configured key: [REDACTED]"]
    assert caplog.messages == expected, "an audiodoc key must not reach the log"


def test_configure_logging_installs_the_secrets_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _configured_handler(monkeypatch)
    installed = any(isinstance(item, SecretsFilter) for item in handler.filters)
    assert installed, "the root handler has no secrets filter"


@pytest.mark.parametrize(
    ("name", "secret"),
    [
        ("BOT_TOKEN", "bot-token-secret-value"),
        ("LLM_API_KEY", "llm-api-key-secret-value"),
        ("AUDIODOC_AUDIO_KEY", "audiodoc-audio-secret"),
        ("AUDIODOC_DOCUMENT_KEY", "audiodoc-document-secret"),
    ],
    ids=["bot-token", "llm-key", "audio-key", "document-key"],
)
def test_configure_logging_redacts_every_configured_secret(
    monkeypatch: pytest.MonkeyPatch, name: str, secret: str
) -> None:
    handler = _configured_handler(monkeypatch, **{name: secret})
    record = logging.LogRecord(
        "bot", logging.ERROR, __file__, 1, "Leaked: <%s>", (secret,), None
    )
    handler.handle(record)
    redacted_line = "Leaked: <[REDACTED]>"
    assert redacted_line in handler.stream.getvalue(), (
        f"{name} must be redacted from the log"
    )


def test_configure_logging_installs_the_correlation_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _configured_handler(monkeypatch)
    installed = any(isinstance(item, CorrelationIdFilter) for item in handler.filters)
    assert installed, "the root handler has no correlation ID filter"


@pytest.mark.parametrize(
    ("context_id", "expected"),
    [
        ("123", " INFO [123] test.correlation: test message"),
        (None, " INFO [-] test.correlation: test message"),
    ],
    ids=["tagged", "untagged"],
)
def test_configure_logging_formats_the_correlation_id(
    monkeypatch: pytest.MonkeyPatch, context_id: str | None, expected: str
) -> None:
    line = _formatted_line(monkeypatch, context_id)
    assert expected in line, "the log line has the wrong correlation ID"
