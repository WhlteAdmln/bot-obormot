# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for log filters."""

import importlib
import logging

import pytest

from bot.utils.log_filters import SecretsFilter


def test_token_is_redacted_from_log_message() -> None:
    """Token is redacted from log message."""
    bot_key = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    log_filter = SecretsFilter([bot_key])
    record = logging.LogRecord(
        "t",
        logging.ERROR,
        "f",
        1,
        f"url=https://api.telegram.org/file/bot{bot_key}/x",
        (),
        None,
    )

    assert log_filter.filter(record) is True
    assert bot_key not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def test_configured_secrets_are_redacted_from_formatted_arguments() -> None:
    """Configured secrets are redacted from formatted arguments."""
    secrets_filter = SecretsFilter(["llm-secret-value", "", "short"])
    record = logging.LogRecord(
        "t",
        logging.ERROR,
        "f",
        1,
        "Request failed: %s",
        ("llm-secret-value",),
        None,
    )

    secrets_filter.filter(record)

    assert "llm-secret-value" not in record.getMessage()
    assert "[REDACTED]" in record.getMessage()


def _fail_download(bot_key: str) -> None:
    msg = f"download failed: https://api.telegram.org/bot{bot_key}/getFile"
    raise RuntimeError(msg)


def test_token_is_redacted_from_exception_traceback() -> None:
    """Token is redacted from exception traceback."""
    bot_key = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    secrets_filter = SecretsFilter([bot_key])

    try:
        _fail_download(bot_key)
    except RuntimeError:
        record = logging.LogRecord(
            "t",
            logging.ERROR,
            "f",
            1,
            "Telegram request failed",
            (),
            __import__("sys").exc_info(),
        )

    secrets_filter.filter(record)

    assert record.exc_text is not None
    assert bot_key not in record.exc_text
    assert "[REDACTED]" in record.exc_text


def test_logging_setup_attaches_filter_to_root_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logging setup attaches filter to root handlers."""
    logging_setup = importlib.import_module("bot.app.logging_setup")

    handler = logging.StreamHandler()
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [handler])
    monkeypatch.setattr(logging, "basicConfig", lambda **_kwargs: None)

    logging_setup.configure_logging()

    assert any(isinstance(item, SecretsFilter) for item in handler.filters)
