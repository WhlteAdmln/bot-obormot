# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat services."""

import asyncio
import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from bot.errors import (
    DocumentAPIError,
    LLMAPIError,
    MediaError,
    WhisperAPIError,
    WhisperEmptyAudioError,
    WhisperError,
)
from bot.services.chat import incoming_log, reporting
from bot.services.chat import locks as chat_locks
from bot.services.chat import pipeline as chat_pipeline
from bot.services.chat.aggregation import aggregator as aggregator_module
from bot.services.chat.aggregation.aggregator import MessageAggregator
from bot.services.chat.errors import catalog, texts
from bot.services.chat.errors import handler as chat_error_handler
from bot.services.chat.formatting import format_roleplay, split_formatted_message
from bot.services.validation import MAX_INPUT_TEXT_LENGTH


def _message(text: str | None, user_id: int | None = 1) -> SimpleNamespace:
    user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(text=text, from_user=user)


def test_format_roleplay_escapes_html_and_applies_markers() -> None:
    """Format roleplay escapes html and applies markers."""
    actual = format_roleplay("  Привет *мир* **важно** ~мысль~ <tag> &  ")

    assert actual == (
        "Привет <i>мир</i> <b>важно</b> "
        "\n<blockquote><i>мысль</i></blockquote>\n "
        "&lt;tag&gt; &amp;"
    )


def test_format_roleplay_keeps_unclosed_and_empty_markers_literal() -> None:
    """Format roleplay keeps unclosed and empty markers literal."""
    assert format_roleplay("текст *незакрыт") == "текст *незакрыт"
    assert format_roleplay("a****b") == "a****b"
    assert format_roleplay("   ") == ""
    assert format_roleplay("") == ""


def test_splitter_closes_and_reopens_html_tags() -> None:
    """Splitter closes and reopens html tags."""
    assert split_formatted_message("<b>abcd</b>", max_length=2) == [
        "<b>ab</b>",
        "<b>cd</b>",
    ]


def test_splitter_preserves_entities_and_utf16_characters() -> None:
    """Splitter preserves entities and utf16 characters."""
    assert split_formatted_message("<b>A&amp;😀B</b>", max_length=3) == [
        "<b>A&amp;</b>",
        "<b>😀B</b>",
    ]


def test_splitter_does_not_split_single_character_larger_than_limit() -> None:
    """Splitter does not split single character larger than limit."""
    assert split_formatted_message("😀", max_length=1) == ["😀"]


def test_splitter_rejects_non_positive_limit() -> None:
    """Splitter rejects non positive limit."""
    with pytest.raises(ValueError, match="max_length"):
        split_formatted_message("text", max_length=0)


@pytest.mark.asyncio
async def test_aggregator_returns_short_standalone_message_immediately() -> None:
    """Aggregator returns short standalone message immediately."""
    aggregator = MessageAggregator()

    assert await aggregator.collect(_message("коротко")) == "коротко"
    assert aggregator._states == {}


@pytest.mark.asyncio
async def test_aggregator_combines_continuation_parts_and_cleans_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aggregator combines continuation parts and cleans state."""
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 2)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.03)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message("первая", 101)))
    await asyncio.sleep(0)
    assert 101 in aggregator._states

    assert await aggregator.collect(_message("вторая", 101)) is None
    assert await asyncio.wait_for(first, timeout=0.5) == "первая\nвторая"
    assert 101 not in aggregator._states


@pytest.mark.asyncio
async def test_aggregator_caps_accumulated_text_and_tracks_background_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aggregator caps accumulated text and tracks background task."""
    monkeypatch.setattr(aggregator_module, "MESSAGE_LENGTH_THRESHOLD", 1)
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.5)
    aggregator = MessageAggregator()

    first = asyncio.create_task(aggregator.collect(_message("x" * 4000, 404)))
    await asyncio.sleep(0)

    assert len(aggregator._tasks) == 1
    background_task = next(iter(aggregator._tasks))
    assert background_task.get_name() == "message_aggregation_404"

    for _ in range(4):
        assert await aggregator.collect(_message("y" * 4000, 404)) is None

    result = await asyncio.wait_for(first, timeout=1.0)
    assert len(result) <= aggregator_module.MAX_INPUT_TEXT_LENGTH + 4096
    assert len(result) > aggregator_module.MAX_INPUT_TEXT_LENGTH

    await asyncio.sleep(0)
    assert aggregator._tasks == set()
    assert 404 not in aggregator._states


@pytest.mark.asyncio
async def test_aggregator_ignores_messages_without_text_or_user() -> None:
    """Aggregator ignores messages without text or user."""
    aggregator = MessageAggregator()

    assert await aggregator.collect(_message(None, 1)) is None
    assert await aggregator.collect(_message("текст", None)) == "текст"


@pytest.mark.asyncio
async def test_user_lock_serializes_same_user_and_releases_registry() -> None:
    """User lock serializes same user and releases registry."""
    first_inside = asyncio.Event()
    release_first = asyncio.Event()
    second_inside = asyncio.Event()

    async def first_worker() -> None:
        async with chat_locks.get_user_lock(202):
            first_inside.set()
            await release_first.wait()

    async def second_worker() -> None:
        async with chat_locks.get_user_lock(202):
            second_inside.set()

    first = asyncio.create_task(first_worker())
    await first_inside.wait()
    assert chat_locks.pending_requests(202) == 1
    second = asyncio.create_task(second_worker())
    await asyncio.sleep(0)
    assert not second_inside.is_set()
    assert chat_locks.pending_requests(202) == 2

    release_first.set()
    await asyncio.gather(first, second)
    assert second_inside.is_set()
    assert chat_locks.pending_requests(202) == 0
    assert 202 not in chat_locks._user_locks


@pytest.mark.asyncio
async def test_user_locks_allow_different_users_to_run_concurrently() -> None:
    """User locks allow different users to run concurrently."""
    async with chat_locks.get_user_lock(301), chat_locks.get_user_lock(302):
        assert 301 in chat_locks._user_locks
        assert 302 in chat_locks._user_locks
    assert 301 not in chat_locks._user_locks
    assert 302 not in chat_locks._user_locks


@pytest.mark.asyncio
async def test_chat_pipeline_streams_calls_callback_and_persists_exchange(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat pipeline streams calls callback and persists exchange."""
    calls = []
    updates = []

    class FakeDatabase:
        async def get_system_prompt(self, user_id: int) -> str:
            calls.append(("system_prompt", user_id))
            return "system"

        async def get_history_limit(self, user_id: int) -> int:
            calls.append(("history_limit", user_id))
            return 12

        async def get_history(self, user_id: int, limit: int | None) -> list[object]:
            calls.append(("history", user_id, limit))
            return [{"role": "user", "content": "old"}]

        async def add_exchange(self, *args: object, **kwargs: object) -> None:
            calls.append(("save", args, kwargs))

        async def prune_history(self, user_id: int) -> None:
            calls.append(("prune", user_id))

    class FakeLLM:
        async def fit_messages_to_context(self, **kwargs: object) -> list[object]:
            calls.append(("fit", kwargs))
            return ["prepared"]

        async def stream(self, messages: object) -> AsyncIterator[str]:
            calls.append(("stream", messages))
            yield "ответ"
            yield " готов"

    async def on_update(text: str) -> None:
        updates.append(text)

    monkeypatch.setattr(chat_pipeline, "db", FakeDatabase())
    monkeypatch.setattr(chat_pipeline, "llm_client", FakeLLM())

    result = await chat_pipeline.process_chat(
        user_id=77,
        user_content="вход",
        saved_user_text="сохранённый вход",
        media=[b"image"],
        on_update=on_update,
    )

    assert result == "ответ готов"
    assert updates == ["ответ", "ответ готов"]
    assert calls[-2] == (
        "save",
        (77, "сохранённый вход", "ответ готов"),
        {"media": [b"image"]},
    )
    assert calls[-1] == ("prune", 77)


@pytest.mark.asyncio
async def test_chat_pipeline_caps_history_limit_at_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat pipeline caps history limit at 100."""
    calls = []

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 500

        async def get_history(self, user_id: int, limit: int | None) -> list[object]:
            calls.append((user_id, limit))
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def prune_history(self, _user_id: object) -> None:
            return None

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            yield "ответ"

    monkeypatch.setattr(chat_pipeline, "db", FakeDatabase())
    monkeypatch.setattr(chat_pipeline, "llm_client", FakeLLM())

    result = await chat_pipeline.process_chat(77, "вход", "вход")

    assert result == "ответ"
    assert calls == [(77, 100)]


@pytest.mark.asyncio
async def test_chat_pipeline_keeps_history_limit_below_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat pipeline keeps history limit below cap."""
    calls = []

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 17

        async def get_history(
            self, _user_id: object, limit: int | None
        ) -> list[object]:
            calls.append(limit)
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def prune_history(self, _user_id: object) -> None:
            return None

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            yield "ответ"

    monkeypatch.setattr(chat_pipeline, "db", FakeDatabase())
    monkeypatch.setattr(chat_pipeline, "llm_client", FakeLLM())

    result = await chat_pipeline.process_chat(77, "вход", "вход")

    assert result == "ответ"
    assert calls == [17]


@pytest.mark.asyncio
async def test_chat_pipeline_does_not_persist_empty_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat pipeline does not persist empty response."""

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 10

        async def get_history(
            self, _user_id: object, limit: int | None
        ) -> list[object]:
            _ = limit  # Passed by keyword; this fake ignores it.
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            msg = "empty response must not be persisted"
            raise AssertionError(msg)

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            if False:
                yield ""

    monkeypatch.setattr(chat_pipeline, "db", FakeDatabase())
    monkeypatch.setattr(chat_pipeline, "llm_client", FakeLLM())

    with pytest.raises(RuntimeError, match="пустой ответ"):
        await chat_pipeline.process_chat(77, "вход", "вход")


def test_chat_error_catalog_preserves_original_if_elif_priority() -> None:
    """Chat error catalog preserves original if elif priority."""
    assert [rule.error_type.__name__ for rule in catalog.CHAT_ERROR_RULES] == [
        "InputTooLongError",
        "TelegramFileTooBigError",
        "DocumentTooLongError",
        "DocumentTimeoutError",
        "DocumentUnavailableError",
        "DocumentAPIError",
        "WhisperEmptyAudioError",
        "WhisperTimeoutError",
        "WhisperUnavailableError",
        "WhisperAPIError",
        "WhisperError",
        "MediaError",
        "TelegramError",
        "LLMTimeoutError",
        "LLMUnavailableError",
        "LLMAPIError",
        "DatabaseError",
    ]


@pytest.mark.asyncio
async def test_chat_error_handler_uses_specific_subclass_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat error handler uses specific subclass rule."""
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
        WhisperEmptyAudioError(),
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
            if rule.error_type is WhisperEmptyAudioError
        )
    ) < catalog.CHAT_ERROR_RULES.index(
        next(
            rule for rule in catalog.CHAT_ERROR_RULES if rule.error_type is WhisperError
        )
    )


@pytest.mark.asyncio
async def test_chat_error_handler_preserves_api_error_log_fields(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Chat error handler preserves api error log fields."""
    captured = []

    async def fake_report(_message: object, _status: object, text: str) -> None:
        captured.append(text)

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)
    error = DocumentAPIError(503, "upstream unavailable")

    with caplog.at_level(logging.ERROR, logger=chat_error_handler.logger.name):
        await chat_error_handler.handle_chat_error(object(), None, 909, error)

    assert captured == [
        "⚠️ Не удалось обработать документ. Проверь его формат или попробуй другой файл."
    ]
    assert (
        "Document Engine API error for user_id=909: HTTP 503, upstream unavailable"
        in caplog.text
    )


@pytest.mark.asyncio
async def test_chat_error_handler_sanitizes_whisper_and_llm_error_bodies(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Chat error handler sanitizes whisper and llm error bodies."""

    async def fake_report(_message: object, _status: object, _text: str) -> None:
        return None

    monkeypatch.setattr(chat_error_handler, "report_error", fake_report)

    with caplog.at_level(logging.ERROR, logger=chat_error_handler.logger.name):
        await chat_error_handler.handle_chat_error(
            object(), None, 909, WhisperAPIError("sensitive\nwhisper response")
        )
        await chat_error_handler.handle_chat_error(
            object(), None, 909, LLMAPIError(503, "sensitive\nllm response")
        )

    assert r"sensitive\nwhisper response" in caplog.text
    assert r"sensitive\nllm response" in caplog.text
    assert "sensitive\nwhisper response" not in caplog.text
    assert "sensitive\nllm response" not in caplog.text


@pytest.mark.asyncio
async def test_chat_error_handler_formats_media_error_and_unknown_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat error handler formats media error and unknown fallback."""
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


@pytest.mark.asyncio
async def test_reporting_answers_when_no_status_and_logs_send_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reporting answers when no status and logs send failure."""

    class FakeMessage:
        async def answer(self, _text: str) -> None:
            msg = "telegram unavailable"
            raise RuntimeError(msg)

    with caplog.at_level(logging.ERROR, logger=reporting.logger.name):
        await reporting.report_error(FakeMessage(), None, "ошибка")

    assert "Could not send error message" in caplog.text


@pytest.mark.asyncio
async def test_reporting_uses_safe_edit_when_status_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reporting uses safe edit when status exists."""
    captured = []

    async def fake_safe_edit(message: object, text: str) -> None:
        captured.append((message, text))

    monkeypatch.setattr(reporting, "safe_edit", fake_safe_edit)
    message = object()
    status = object()

    await reporting.report_error(message, status, "ошибка")
    assert captured == [(status, "ошибка")]


def test_incoming_log_records_message_types(caplog: pytest.LogCaptureFixture) -> None:
    """Incoming log records message types."""
    document = SimpleNamespace(file_name="doc.pdf", mime_type="application/pdf")
    animation = SimpleNamespace(mime_type="image/gif", file_id="gif-id")
    message = SimpleNamespace(
        content_type="document",
        animation=animation,
        video=None,
        document=document,
        sticker=None,
        photo=None,
    )

    with caplog.at_level(logging.INFO, logger=incoming_log.logger.name):
        incoming_log.log_incoming_message(message)

    assert "INCOMING MESSAGE: type=document" in caplog.text
    assert "DOCUMENT INFO: filename=doc.pdf" in caplog.text
    assert "ANIMATION INFO: mime_type=image/gif" in caplog.text


def test_incoming_log_sanitizes_user_supplied_document_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Incoming log sanitizes user supplied document metadata."""
    document = SimpleNamespace(
        file_name="report.pdf\nERROR forged entry",
        mime_type="application/pdf\rINFO forged entry",
    )
    message = SimpleNamespace(
        content_type="document",
        animation=None,
        video=None,
        document=document,
        sticker=None,
        photo=None,
    )

    with caplog.at_level(logging.INFO, logger=incoming_log.logger.name):
        incoming_log.log_incoming_message(message)

    assert r"filename=report.pdf\nERROR forged entry" in caplog.text
    assert r"mime_type=application/pdf\rINFO forged entry" in caplog.text
    assert "\nERROR forged entry" not in caplog.text
    assert "\rINFO forged entry" not in caplog.text


def test_chat_services_are_loaded_from_canonical_modules() -> None:
    """Chat services are loaded from canonical modules."""
    assert incoming_log.__name__ == "bot.services.chat.incoming_log"
    assert chat_pipeline.__name__ == "bot.services.chat.pipeline"
    assert reporting.__name__ == "bot.services.chat.reporting"
    assert chat_error_handler.__name__ == "bot.services.chat.errors.handler"
    assert aggregator_module.__name__ == "bot.services.chat.aggregation.aggregator"


@pytest.mark.asyncio
async def test_chat_pipeline_returns_response_when_history_pruning_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat pipeline returns response when history pruning fails."""

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 10

        async def get_history(
            self, _user_id: object, limit: int | None
        ) -> list[object]:
            _ = limit  # Passed by keyword; this fake ignores it.
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def prune_history(self, _user_id: object) -> None:
            msg = "test prune failure"
            raise RuntimeError(msg)

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            yield "ответ"

    monkeypatch.setattr(chat_pipeline, "db", FakeDatabase())
    monkeypatch.setattr(chat_pipeline, "llm_client", FakeLLM())

    assert await chat_pipeline.process_chat(77, "вход", "вход") == "ответ"


def test_user_facing_length_errors_use_configured_input_limit() -> None:
    """User facing length errors use configured input limit."""
    expected_limit = str(MAX_INPUT_TEXT_LENGTH)
    input_message = texts.input_too_long(Exception())
    document_message = texts.document_too_long(Exception())

    assert expected_limit in input_message.replace(" ", "")
    assert expected_limit in document_message.replace(" ", "")
