# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for log filters."""

import importlib
import logging

import pytest

from bot_obormot.log_filters import SecretsFilter
from tests.support.settings import make_settings


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
    expected_fragment = "[REDACTED]"
    assert expected_fragment in record.getMessage()


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

    expected_fragment = "llm-secret-value"
    assert expected_fragment not in record.getMessage()
    expected_fragment = "[REDACTED]"
    assert expected_fragment in record.getMessage()


def _fail_download(bot_key: str) -> None:
    msg = f"download failed: https://api.telegram.org/bot{bot_key}/getFile"
    raise RuntimeError(msg)


def test_token_is_redacted_from_exception_traceback() -> None:
    """Token is redacted from exception traceback."""
    bot_key = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    secrets_filter = SecretsFilter([bot_key])

    with pytest.raises(RuntimeError) as caught:
        _fail_download(bot_key)
    error = caught.value
    record = logging.LogRecord(
        "t",
        logging.ERROR,
        "f",
        1,
        "Telegram request failed",
        (),
        (type(error), error, error.__traceback__),
    )

    secrets_filter.filter(record)

    exc_text = str(record.exc_text)
    assert bot_key not in exc_text
    expected_fragment = "[REDACTED]"
    assert expected_fragment in exc_text


def test_logging_setup_attaches_filter_to_root_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logging setup attaches filter to root handlers."""
    logging_setup = importlib.import_module("bot_obormot.app.logging_setup")

    handler = logging.StreamHandler()
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [handler])
    monkeypatch.setattr(logging, "basicConfig", lambda **_kwargs: None)

    logging_setup.configure_logging(make_settings())

    assert any(isinstance(item, SecretsFilter) for item in handler.filters)


@pytest.mark.parametrize(
    "message",
    [
        "Authorization: Bearer first-secret-value",
        "authorization=Bearer second-secret-value",
        "Bearer third-secret-value",
    ],
)
def test_bearer_tokens_are_redacted(message: str) -> None:
    """Bearer values are redacted with or without an authorization prefix."""
    log_filter = SecretsFilter([])
    record = logging.LogRecord("t", logging.ERROR, "f", 1, message, (), None)

    assert log_filter.filter(record) is True
    expected_fragment = "secret-value"
    assert expected_fragment not in record.getMessage()
    expected_fragment = "[REDACTED]"
    assert expected_fragment in record.getMessage()


def test_logging_setup_redacts_every_configured_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Logging setup redacts every secret supplied by application settings."""
    logging_setup = importlib.import_module("bot_obormot.app.logging_setup")
    secrets = [
        "bot-token-secret-value",
        "llm-api-key-secret-value",
        "audiodoc-audio-secret",
        "audiodoc-document-secret",
    ]
    settings = make_settings(
        BOT_TOKEN=secrets[0],
        LLM_API_KEY=secrets[1],
        AUDIODOC_AUDIO_KEY=secrets[2],
        AUDIODOC_DOCUMENT_KEY=secrets[3],
    )

    handler = logging.StreamHandler()
    root_logger = logging.getLogger()
    monkeypatch.setattr(root_logger, "handlers", [handler])
    monkeypatch.setattr(logging, "basicConfig", lambda **_kwargs: None)

    logging_setup.configure_logging(settings)

    secrets_filter = next(
        item for item in handler.filters if isinstance(item, SecretsFilter)
    )
    record = logging.LogRecord(
        "t",
        logging.ERROR,
        "f",
        1,
        "Configured secrets: %s",
        (" ".join(secrets),),
        None,
    )

    assert secrets_filter.filter(record) is True
    cleaned_message = record.getMessage()
    assert all(secret not in cleaned_message for secret in secrets)
    assert cleaned_message.count("[REDACTED]") == len(secrets)
