# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Characterization tests for the package-based chat handler.

The handler dependencies are replaced on the real handler module so these
tests focus on ordering, stream lifecycle, cancellation, and task cleanup
without requiring a running Telegram/LLM service.
"""

import asyncio
from types import SimpleNamespace

import pytest

from bot_obormot.handlers.chat import handler as handler_module
from bot_obormot.services.chat.aggregation import AggregatedText
from bot_obormot.services.telegram import TelegramDownloader
from bot_obormot.settings import Settings
from tests.support.chat_handler import (
    RecordingAggregator,
    RecordingTokenCounter,
    RecordingUserLocks,
)
from tests.support.chat_streaming import single_answer
from tests.support.settings import make_settings

SETTINGS = make_settings()


def _create_chat_handler_state() -> SimpleNamespace:
    calls: list[object] = []
    user_locks = RecordingUserLocks(calls)
    aggregator = RecordingAggregator(calls)
    return SimpleNamespace(
        calls=calls,
        typing_started=asyncio.Event(),
        typing_stopped=asyncio.Event(),
        lock_entered=user_locks.entered,
        user_locks=user_locks,
        safe_edits=[],
        error_calls=[],
        pipeline=SimpleNamespace(),
        aggregator=aggregator,
        chat_runtime=handler_module.ChatRuntime(
            message_aggregator=aggregator,
            user_locks=user_locks,
            downloader=TelegramDownloader(),
        ),
        llm_client=RecordingTokenCounter(calls),
        database=object(),
    )


def _patch_input_stubs(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[object],
) -> None:
    def log_incoming(_message: object) -> None:
        calls.append("log")

    def inspect(_message: object) -> SimpleNamespace:
        calls.append("inspect")
        return SimpleNamespace(
            has_content=True,
            has_text=True,
            has_media=False,
            has_audio=False,
            has_document=False,
        )

    async def prepare(
        _message: object,
        _info: object,
        text_override: str | None = None,
        settings: Settings | None = None,
        *,
        downloader: object,
    ) -> SimpleNamespace:
        assert isinstance(downloader, TelegramDownloader)
        assert settings is SETTINGS
        calls.append(("prepare", text_override))
        await asyncio.sleep(0)
        return SimpleNamespace(
            user_content="prepared user content",
            saved_user_text="saved user text",
            image_bytes=None,
        )

    monkeypatch.setattr(handler_module, "log_incoming_message", log_incoming)
    monkeypatch.setattr(handler_module, "inspect_message", inspect)
    monkeypatch.setattr(handler_module, "prepare_message", prepare)


def _patch_typing_stub(
    monkeypatch: pytest.MonkeyPatch,
    typing_started: asyncio.Event,
    typing_stopped: asyncio.Event,
) -> None:
    async def keep_typing(_message: object) -> None:
        typing_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            typing_stopped.set()
            raise

    monkeypatch.setattr(handler_module, "keep_typing", keep_typing)


def _patch_processing_stubs(
    monkeypatch: pytest.MonkeyPatch,
    state: SimpleNamespace,
) -> None:
    async def process_chat(**kwargs: object) -> object:
        state.calls.append("process")
        process = state.pipeline.process
        return await process(kwargs)

    state.pipeline.process = lambda _kwargs: None
    monkeypatch.setattr(handler_module, "process_chat", process_chat)


def _patch_reporting_stubs(
    monkeypatch: pytest.MonkeyPatch,
    state: SimpleNamespace,
) -> None:
    async def safe_edit(
        message: object,
        text: str,
        parse_mode: str | None = None,
    ) -> None:
        state.safe_edits.append((message, text, parse_mode))

    async def handle_error(**kwargs: object) -> None:
        state.error_calls.append(kwargs)

    monkeypatch.setattr(handler_module, "handle_chat_error", handle_error)
    monkeypatch.setattr(handler_module, "safe_edit", safe_edit)


@pytest.fixture(name="state")
def fixture_state(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace the chat handler dependencies and expose the recorded state."""
    result = _create_chat_handler_state()
    _patch_input_stubs(monkeypatch, result.calls)
    _patch_typing_stub(monkeypatch, result.typing_started, result.typing_stopped)
    _patch_processing_stubs(monkeypatch, result)
    _patch_reporting_stubs(monkeypatch, result)
    return result


class Message:
    """Message."""

    def __init__(
        self,
        text: str = "text",
        user_id: int = 7,
        message_id: int | None = None,
    ) -> None:
        """Initializes the test double."""
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.message_id = message_id
        self.chat = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text: str, **kwargs: object) -> SimpleNamespace:
        """Answer."""
        self.answers.append((text, kwargs))
        return SimpleNamespace(text=text)


@pytest.mark.asyncio
async def test_handler_preserves_order_for_short_non_streamed_response(
    state: SimpleNamespace,
) -> None:
    message = Message()

    async def process(kwargs: object) -> str:
        expected_user_id = 7
        assert kwargs["user_id"] == expected_user_id
        expected_user_content = "prepared user content"
        assert kwargs["user_content"] == expected_user_content
        return "короткий ответ"

    state.pipeline.process = process

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    assert message.answers == [("короткий ответ", {})]
    assert state.calls[:5] == [
        "log",
        "inspect",
        "aggregate",
        "lock-enter",
        ("prepare", "входящий текст"),
    ]
    assert state.calls.index("process") > state.calls.index(
        ("prepare", "входящий текст")
    )
    assert state.typing_started.is_set()
    assert state.typing_stopped.is_set()
    expected_calls = "lock-exit"
    assert state.calls[-1] == expected_calls


@pytest.mark.asyncio
async def test_handler_streams_long_response_and_finalizes_status(
    state: SimpleNamespace,
) -> None:
    message = Message()

    async def process(kwargs: object) -> str:
        await kwargs["on_update"]("A" * 300)
        await asyncio.sleep(0.81)
        await kwargs["on_update"]("B" * 300)
        return "Итоговый ответ"

    state.pipeline.process = process

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    expected_count = 2
    assert len(state.safe_edits) == expected_count
    expected_safe_edits = "Итоговый ответ"
    assert state.safe_edits[-1][1] == expected_safe_edits
    assert message.answers == [("A" * 300, {})]
    assert state.typing_stopped.is_set()


@pytest.mark.asyncio
async def test_handler_cancellation_updates_status_and_cleans_typing_task(
    state: SimpleNamespace,
) -> None:
    message = Message()

    async def process(kwargs: object) -> None:
        await kwargs["on_update"]("X" * 300)
        raise asyncio.CancelledError

    state.pipeline.process = process

    with pytest.raises(asyncio.CancelledError):
        await handler_module.handle_message(
            message,
            llm_client=state.llm_client,
            database=state.database,
            chat_runtime=state.chat_runtime,
            settings=SETTINGS,
        )

    expected_safe_edits = "⏹ Запрос отменён."
    assert state.safe_edits[-1][1] == expected_safe_edits
    assert state.typing_started.is_set()
    assert state.typing_stopped.is_set()
    expected_calls = "lock-exit"
    assert state.calls[-1] == expected_calls


@pytest.mark.asyncio
async def test_handler_returns_early_for_aggregated_continuation(
    state: SimpleNamespace,
) -> None:
    message = Message()
    state.aggregator.result = None

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    assert state.calls == ["log", "inspect", "aggregate"]
    assert not state.lock_entered.is_set()
    expected_empty = []
    assert message.answers == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_handler_rejects_user_when_pending_request_limit_is_reached(
    state: SimpleNamespace,
) -> None:
    message = Message()
    state.user_locks.pending_count = 3

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    assert message.answers == [
        ("⏳ Я ещё обрабатываю твои предыдущие сообщения. Подожди немного.", {})
    ]
    lock_event = "lock-enter"
    assert lock_event not in state.calls
    assert not state.typing_started.is_set()


@pytest.mark.asyncio
async def test_handler_routes_processing_error_to_central_error_handler(
    state: SimpleNamespace,
) -> None:
    message = Message()

    async def process(_kwargs: object) -> None:
        msg = "pipeline failed"
        raise RuntimeError(msg)

    state.pipeline.process = process

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    assert len(state.error_calls) == 1
    error = state.error_calls[0]
    assert error["message"] is message
    expected_user_id = 7
    assert error["user_id"] == expected_user_id
    assert isinstance(error["error"], RuntimeError)
    assert state.typing_stopped.is_set()


@pytest.mark.asyncio
async def test_handler_preserves_final_answer_after_stream_edit_failure(
    state: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = Message()

    async def broken_edit(
        _status: object,
        _text: str,
        **_kwargs: object,
    ) -> None:
        msg = "telegram edit failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(handler_module, "safe_edit", broken_edit)

    async def process(kwargs: object) -> str:
        await kwargs["on_update"]("A" * 300)
        await asyncio.sleep(0.81)
        await kwargs["on_update"]("B" * 300)
        return "Финальный ответ не должен потеряться"

    state.pipeline.process = process

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    assert message.answers == [
        ("A" * 300, {}),
        ("Финальный ответ не должен потеряться", {}),
    ]
    assert state.typing_stopped.is_set()


@pytest.mark.asyncio
async def test_handler_routes_llm_connection_loss_with_existing_status(
    state: SimpleNamespace,
) -> None:
    message = Message()

    async def process(kwargs: object) -> None:
        await kwargs["on_update"]("S" * 300)
        msg = "llama-server stopped"
        raise ConnectionError(msg)

    state.pipeline.process = process

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    assert len(state.error_calls) == 1
    error = state.error_calls[0]
    assert error["message"] is message
    assert error["status"].text == "S" * 300
    assert isinstance(error["error"], ConnectionError)
    assert state.typing_stopped.is_set()


@pytest.mark.asyncio
async def test_handler_replies_to_the_incoming_message(
    state: SimpleNamespace,
) -> None:
    message = Message(message_id=11)

    async def process(_kwargs: object) -> str:
        return "**ответ**"

    state.pipeline.process = process

    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    text, kwargs = single_answer(message)
    expected_text = "*ответ*"
    assert text == expected_text
    expected_parse_mode = "MarkdownV2"
    assert kwargs["parse_mode"] == expected_parse_mode
    expected_message_id = 11
    assert kwargs["reply_parameters"].message_id == expected_message_id
    assert kwargs["reply_parameters"].allow_sending_without_reply is True


@pytest.mark.asyncio
async def test_handler_replies_to_the_last_aggregated_message(
    state: SimpleNamespace,
) -> None:
    first = Message(message_id=11)
    last = Message(message_id=13)
    state.aggregator.result = AggregatedText("первая\nтретья", last)

    async def process(_kwargs: object) -> str:
        return "ответ"

    state.pipeline.process = process

    await handler_module.handle_message(
        first,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=SETTINGS,
    )

    text, kwargs = single_answer(first)
    expected_text = "ответ"
    assert text == expected_text
    parse_mode_field = "parse_mode"
    assert parse_mode_field not in kwargs
    expected_message_id = 13
    assert kwargs["reply_parameters"].message_id == expected_message_id
