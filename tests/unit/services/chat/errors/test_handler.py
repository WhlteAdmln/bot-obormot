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


@pytest.mark.asyncio
async def test_chat_error_handler_uses_specific_subclass_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []

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

    assert captured == [
        (
            message,
            status,
            (
                "🎤 Не удалось распознать речь. "
                "Попробуй записать голосовое сообщение ещё раз."
            ),
        )
    ]
    assert catalog.CHAT_ERROR_RULES.index(
        next(
            rule
            for rule in catalog.CHAT_ERROR_RULES
            if rule.error_type is AudiodocEmptyAudioError
        )
    ) < catalog.CHAT_ERROR_RULES.index(
        next(
            rule
            for rule in catalog.CHAT_ERROR_RULES
            if rule.error_type is AudiodocError
        )
    )


@pytest.mark.asyncio
async def test_chat_error_handler_preserves_api_error_log_fields(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    captured = []

    async def fake_report(_message: object, _status: object, text: str) -> None:
        captured.append(text)

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)
    error = DocumentAPIError(503, "upstream unavailable")

    with caplog.at_level(logging.ERROR, logger=chat_error_handler.logger.name):
        await chat_error_handler.handle_chat_error(object(), None, 909, error)

    assert captured == [
        (
            "⚠️ Не удалось обработать документ. "
            "Проверь его формат или попробуй другой файл."
        )
    ]
    api_error_line = (
        "Document Engine API error for user_id=909: HTTP 503, upstream unavailable"
    )
    assert api_error_line in caplog.text


@pytest.mark.asyncio
async def test_chat_error_handler_sanitizes_audiodoc_and_llm_error_bodies(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:

    async def fake_report(_message: object, _status: object, _text: str) -> None:
        return None

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)

    with caplog.at_level(logging.ERROR, logger=chat_error_handler.logger.name):
        await chat_error_handler.handle_chat_error(
            object(), None, 909, AudiodocAPIError("sensitive\nwhisper response")
        )
        await chat_error_handler.handle_chat_error(
            object(), None, 909, LLMAPIError(503, "sensitive\nllm response")
        )

    escaped_whisper_body = r"sensitive\nwhisper response"
    assert escaped_whisper_body in caplog.text
    escaped_llm_body = r"sensitive\nllm response"
    assert escaped_llm_body in caplog.text
    raw_whisper_body = "sensitive\nwhisper response"
    assert raw_whisper_body not in caplog.text
    raw_llm_body = "sensitive\nllm response"
    assert raw_llm_body not in caplog.text


@pytest.mark.asyncio
async def test_chat_error_handler_formats_media_error_and_unknown_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = []

    async def fake_report(_message: object, _status: object, text: str) -> None:
        captured.append(text)

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)

    await chat_error_handler.handle_chat_error(
        object(), None, 1, MediaError("bad media")
    )
    await chat_error_handler.handle_chat_error(object(), None, 1, ValueError("unknown"))

    assert captured == [
        "⚠️ bad media",
        "❌ Произошла непредвиденная ошибка. Попробуй ещё раз.",
    ]
