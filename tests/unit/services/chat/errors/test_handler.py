# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for errors handler."""

import logging

import pytest

from bot_obormot.errors import (
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocError,
    DocumentAPIError,
    LLMAPIError,
    MediaError,
)
from bot_obormot.services.chat.errors import catalog
from bot_obormot.services.chat.errors import handler as chat_error_handler


def _capture_reports(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace the error reporter and collect the reported texts."""
    captured: list[str] = []

    async def fake_report(_message: object, _status: object, text: str) -> None:
        captured.append(text)

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)
    return captured


def _rule_index(error_type: type[Exception]) -> int:
    """Return the position of the rule for an error type."""
    return catalog.CHAT_ERROR_RULES.index(
        next(rule for rule in catalog.CHAT_ERROR_RULES if rule.error_type is error_type)
    )


@pytest.mark.asyncio
async def test_chat_error_handler_uses_specific_subclass_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[object, object, str]] = []

    async def fake_report(message: object, status: object, text: str) -> None:
        captured.append((message, status, text))

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)
    message = object()
    status = object()

    await chat_error_handler.handle_chat_error(
        message,
        status,
        88,
        AudiodocEmptyAudioError(),
    )

    expected = [
        (
            message,
            status,
            (
                "🎤 Не удалось распознать речь. "
                "Попробуй записать голосовое сообщение ещё раз."
            ),
        )
    ]
    assert captured == expected, "the subclass rule was not used"


def test_chat_error_rules_list_the_subclass_before_its_parent() -> None:
    subclass_index = _rule_index(AudiodocEmptyAudioError)
    parent_index = _rule_index(AudiodocError)
    assert subclass_index < parent_index, "the parent rule shadows the subclass"


@pytest.mark.asyncio
async def test_chat_error_handler_reports_document_api_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_reports(monkeypatch)
    error = DocumentAPIError(503, "upstream unavailable")

    await chat_error_handler.handle_chat_error(object(), None, 909, error)

    expected = [
        (
            "⚠️ Не удалось обработать документ. "
            "Проверь его формат или попробуй другой файл."
        )
    ]
    assert captured == expected, "the document error text differs"


@pytest.mark.asyncio
async def test_chat_error_handler_preserves_api_error_log_fields(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _capture_reports(monkeypatch)
    error = DocumentAPIError(502, "bad gateway")

    with caplog.at_level(logging.ERROR, logger=chat_error_handler.logger.name):
        await chat_error_handler.handle_chat_error(object(), None, 707, error)

    api_error_line = "Document Engine API error for user_id=707: HTTP 502, bad gateway"
    assert api_error_line in caplog.text, "the API error fields are not logged"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "escaped_body"),
    [
        (
            AudiodocAPIError("sensitive\nwhisper response"),
            r"sensitive\nwhisper response",
        ),
        (LLMAPIError(503, "sensitive\nllm response"), r"sensitive\nllm response"),
    ],
)
async def test_chat_error_handler_logs_escaped_error_bodies(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    escaped_body: str,
) -> None:
    _capture_reports(monkeypatch)

    with caplog.at_level(logging.ERROR, logger=chat_error_handler.logger.name):
        await chat_error_handler.handle_chat_error(object(), None, 909, error)

    assert escaped_body in caplog.text, "the escaped error body is not logged"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "raw_body"),
    [
        (AudiodocAPIError("secret\nwhisper body"), "secret\nwhisper body"),
        (LLMAPIError(500, "secret\nllm body"), "secret\nllm body"),
    ],
)
async def test_chat_error_handler_sanitizes_audiodoc_and_llm_error_bodies(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    raw_body: str,
) -> None:
    _capture_reports(monkeypatch)

    with caplog.at_level(logging.ERROR, logger=chat_error_handler.logger.name):
        await chat_error_handler.handle_chat_error(object(), None, 808, error)

    assert raw_body not in caplog.text, "a raw error body was logged"


@pytest.mark.asyncio
async def test_chat_error_handler_formats_media_error_and_unknown_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _capture_reports(monkeypatch)

    await chat_error_handler.handle_chat_error(
        object(), None, 1, MediaError("bad media")
    )
    await chat_error_handler.handle_chat_error(object(), None, 1, ValueError("unknown"))

    expected = [
        "⚠️ bad media",
        "❌ Произошла непредвиденная ошибка. Попробуй ещё раз.",
    ]
    assert captured == expected, "the media or fallback text differs"
