# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for log filters."""

import logging

import pytest

from bot_obormot.log_filters import SecretsFilter


def _record(message: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("bot", logging.ERROR, "bot.py", 7, message, args, None)


def _cleaned(secrets: list[str], message: str, *args: object) -> str:
    record = _record(message, *args)
    SecretsFilter(secrets).filter(record)
    return record.getMessage()


def _fail_download(bot_key: str) -> None:
    msg = f"download failed: https://api.telegram.org/bot{bot_key}/getFile"
    raise RuntimeError(msg)


def test_filter_keeps_every_record() -> None:
    record = _record("Authorization: Bearer kept-record-value")
    assert SecretsFilter(["kept-record-value"]).filter(record) is True, (
        "the filter must redact, not drop, a record"
    )


@pytest.mark.parametrize(
    "bot_key",
    [
        "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789",
        "987654:" + "x_Z" * 12,
        "100200300400:" + "Q" * 30,
    ],
    ids=["typical", "short-id", "long-id"],
)
def test_filter_redacts_a_telegram_token_it_was_not_given(bot_key: str) -> None:
    message = f"token {bot_key} was rejected"
    expected = "token [REDACTED] was rejected"
    assert _cleaned([], message) == expected, "a token-like value must be redacted"


def test_filter_redacts_a_configured_secret_from_formatted_arguments() -> None:
    cleaned = _cleaned(["llm-secret-value"], "Request failed: %s", "llm-secret-value")
    expected = "Request failed: [REDACTED]"
    assert cleaned == expected, "a secret in the arguments must be redacted"


@pytest.mark.parametrize(
    "secret",
    ["", "short", "1234567"],
    ids=["empty", "five-chars", "seven-chars"],
)
def test_filter_ignores_secrets_shorter_than_eight_characters(secret: str) -> None:
    message = "status short 1234567 ok"
    assert _cleaned([secret], message) == message, (
        "a too short secret must not mangle ordinary text"
    )


def test_filter_redacts_every_occurrence_of_a_secret() -> None:
    cleaned = _cleaned(["k3y-v4lue-x"], "a=k3y-v4lue-x b=k3y-v4lue-xk3y-v4lue-x")
    expected = "a=[REDACTED] b=[REDACTED][REDACTED]"
    assert cleaned == expected, "every occurrence must be redacted"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            "Authorization: Bearer first-secret-value",
            "Authorization: Bearer [REDACTED]",
        ),
        (
            "authorization=Bearer second-secret-value",
            "authorization=Bearer [REDACTED]",
        ),
        ("Bearer third-secret-value", "Bearer [REDACTED]"),
        ("AUTHORIZATION : BEARER fourth.secret", "AUTHORIZATION : BEARER [REDACTED]"),
        ("h={'Bearer x9y8z7', 'next'}", "h={'Bearer [REDACTED], 'next'}"),
        (
            "Bearer one-secret, Bearer two-secret;",
            "Bearer [REDACTED], Bearer [REDACTED];",
        ),
    ],
    ids=["header", "assignment", "bare", "upper-case", "in-repr", "two-values"],
)
def test_filter_redacts_bearer_values(message: str, expected: str) -> None:
    assert _cleaned([], message) == expected, "a Bearer value must be redacted"


def test_filter_redacts_a_secret_split_across_message_and_arguments() -> None:
    cleaned = _cleaned(["prefix-and-suffix"], "key=prefix-%s", "and-suffix")
    expected = "key=[REDACTED]"
    assert cleaned == expected, "the rendered message must be redacted"


def test_filter_leaves_a_clean_record_untouched() -> None:
    record = _record("User %s sent %d photos", 42, 3)
    SecretsFilter(["unrelated-secret"]).filter(record)
    observed = (record.msg, record.args)
    expected = ("User %s sent %d photos", (42, 3))
    assert observed == expected, "a clean record must keep its arguments"


def test_filter_redacts_a_token_from_an_exception_traceback() -> None:
    bot_key = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ0123456789"
    with pytest.raises(RuntimeError) as caught:
        _fail_download(bot_key)
    error = caught.value
    record = logging.LogRecord(
        "bot",
        logging.ERROR,
        "bot.py",
        7,
        "Telegram request failed",
        (),
        (type(error), error, error.__traceback__),
    )
    SecretsFilter([bot_key]).filter(record)
    redacted_url = "bot[REDACTED]/getFile"
    assert redacted_url in str(record.exc_text), "the traceback must not keep the token"


def test_filter_redacts_a_secret_from_an_existing_exception_text() -> None:
    record = _record("Upload failed")
    record.exc_text = "Traceback: api_key=abcdefgh-ijkl in request"
    SecretsFilter(["abcdefgh-ijkl"]).filter(record)
    expected = "Traceback: api_key=[REDACTED] in request"
    assert record.exc_text == expected, "a formatted traceback must be redacted"
