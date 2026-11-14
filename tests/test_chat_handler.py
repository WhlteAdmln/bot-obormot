# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Characterization tests for the package-based chat handler.

The handler dependencies are stubbed so these tests focus on ordering,
stream lifecycle, cancellation, and task cleanup without requiring aiogram
or a running Telegram/LLM service.
"""

import asyncio
import importlib
import sys
import types
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


def _install_module(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    **attributes: object,
) -> types.ModuleType:
    result = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(result, key, value)
    monkeypatch.setitem(sys.modules, name, result)
    return result


class _TestAggregator:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls
        self.result: str | None = "входящий текст"

    async def collect(self, _message: object) -> str | None:
        self.calls.append("aggregate")
        return self.result


class _TestLLM:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls

    async def count_text_tokens(self, _text: str) -> int:
        self.calls.append("count-tokens")
        return 151


def _create_chat_handler_state() -> SimpleNamespace:
    calls: list[object] = []
    return SimpleNamespace(
        calls=calls,
        typing_started=asyncio.Event(),
        typing_stopped=asyncio.Event(),
        lock_entered=asyncio.Event(),
        safe_edits=[],
        error_calls=[],
        pipeline=SimpleNamespace(),
        aggregator=_TestAggregator(calls),
    )


def _install_aiogram_stubs(monkeypatch: pytest.MonkeyPatch) -> types.ModuleType:
    class Router:
        def message(self, *_args: object, **_kwargs: object) -> object:
            return lambda function: function

    aiogram = _install_module(monkeypatch, "aiogram", Router=Router)
    _install_module(monkeypatch, "aiogram.types", Message=object)
    return aiogram


def _install_input_stubs(
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
    ) -> SimpleNamespace:
        calls.append(("prepare", text_override))
        await asyncio.sleep(0)
        return SimpleNamespace(
            user_content="prepared user content",
            saved_user_text="saved user text",
            image_bytes=None,
        )

    _install_module(
        monkeypatch,
        "bot.services.chat.incoming_log",
        log_incoming_message=log_incoming,
    )
    _install_module(
        monkeypatch,
        "bot.services.chat.input",
        inspect_message=inspect,
        prepare_message=prepare,
    )


def _install_lock_stub(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[object],
    lock_entered: asyncio.Event,
) -> None:
    @asynccontextmanager
    async def user_lock(_user_id: int) -> AsyncIterator[None]:
        calls.append("lock-enter")
        lock_entered.set()
        try:
            yield
        finally:
            calls.append("lock-exit")

    _install_module(
        monkeypatch,
        "bot.services.chat.locks",
        get_user_lock=user_lock,
        pending_requests=lambda _user_id: 0,
    )


def _install_typing_stub(
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

    _install_module(
        monkeypatch,
        "bot.services.telegram.chat_action",
        keep_typing=keep_typing,
    )


def _install_processing_stubs(
    monkeypatch: pytest.MonkeyPatch,
    state: SimpleNamespace,
) -> None:
    async def process_chat(**kwargs: object) -> object:
        state.calls.append("process")
        process = state.pipeline.process
        return await process(kwargs)

    state.pipeline.process = lambda _kwargs: None
    _install_module(
        monkeypatch,
        "bot.services.chat.pipeline",
        process_chat=process_chat,
    )
    _install_module(
        monkeypatch,
        "bot.services.llm",
        llm_client=_TestLLM(state.calls),
    )


def _install_reporting_stubs(
    monkeypatch: pytest.MonkeyPatch,
    state: SimpleNamespace,
) -> None:
    async def safe_edit(message: object, text: str) -> None:
        state.safe_edits.append((message, text))

    async def handle_error(**kwargs: object) -> None:
        state.error_calls.append(kwargs)

    _install_module(
        monkeypatch,
        "bot.services.chat.errors.handler",
        handle_chat_error=handle_error,
    )
    _install_module(
        monkeypatch,
        "bot.services.chat.reporting",
        safe_edit=safe_edit,
    )


def _install_chat_service_stubs(
    monkeypatch: pytest.MonkeyPatch,
    state: SimpleNamespace,
) -> None:
    _install_module(
        monkeypatch,
        "bot.services.chat.aggregation",
        message_aggregator=state.aggregator,
    )
    _install_input_stubs(monkeypatch, state.calls)
    _install_lock_stub(monkeypatch, state.calls, state.lock_entered)
    _install_typing_stub(
        monkeypatch,
        state.typing_started,
        state.typing_stopped,
    )
    _install_processing_stubs(monkeypatch, state)
    _install_reporting_stubs(monkeypatch, state)


def _load_chat_handler_package(
    state: SimpleNamespace,
) -> tuple[types.ModuleType, types.ModuleType]:
    sys.modules.pop("bot.handlers.chat.handler", None)
    sys.modules.pop("bot.handlers.chat", None)
    handlers_module = importlib.import_module("bot.handlers")

    if hasattr(handlers_module, "chat"):
        delattr(handlers_module, "chat")

    package = importlib.import_module("bot.handlers.chat")
    package._test_calls = state.calls
    package._test_typing_started = state.typing_started
    package._test_typing_stopped = state.typing_stopped
    package._test_lock_entered = state.lock_entered
    package._test_safe_edits = state.safe_edits
    package._test_error_calls = state.error_calls
    package._test_pipeline = state.pipeline
    package._test_aggregator = state.aggregator
    package._test_aiogram = state.aiogram
    return package, handlers_module


def _cleanup_chat_handler_package(handlers_module: types.ModuleType) -> None:
    sys.modules.pop("bot.handlers.chat.handler", None)
    sys.modules.pop("bot.handlers.chat", None)
    if hasattr(handlers_module, "chat"):
        delattr(handlers_module, "chat")


@pytest.fixture
def chat_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[types.ModuleType, None, None]:
    """Chat handler."""
    state = _create_chat_handler_state()
    state.aiogram = _install_aiogram_stubs(monkeypatch)
    _install_chat_service_stubs(monkeypatch, state)
    package, handlers_module = _load_chat_handler_package(state)

    try:
        yield package
    finally:
        _cleanup_chat_handler_package(handlers_module)


class Message:
    """Message."""

    def __init__(self, text: str = "text", user_id: int = 7) -> None:
        """Initializes the test double."""
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text: str, **kwargs: object) -> SimpleNamespace:
        """Answer."""
        self.answers.append((text, kwargs))
        return SimpleNamespace(text=text)


@pytest.mark.asyncio
async def test_handler_preserves_order_for_short_non_streamed_response(
    chat_handler: object,
) -> None:
    """Handler preserves order for short non streamed response."""
    message = Message()

    async def process(kwargs: object) -> str:
        assert kwargs["user_id"] == 7
        assert kwargs["user_content"] == "prepared user content"
        return "короткий ответ"

    chat_handler._test_pipeline.process = process

    await chat_handler.handle_message(message)

    assert message.answers == [("короткий ответ", {"parse_mode": "HTML"})]
    assert chat_handler._test_calls[:5] == [
        "log",
        "inspect",
        "aggregate",
        "lock-enter",
        ("prepare", "входящий текст"),
    ]
    assert chat_handler._test_calls.index("process") > chat_handler._test_calls.index(
        ("prepare", "входящий текст")
    )
    assert chat_handler._test_typing_started.is_set()
    assert chat_handler._test_typing_stopped.is_set()
    assert chat_handler._test_calls[-1] == "lock-exit"


@pytest.mark.asyncio
async def test_handler_streams_long_response_and_finalizes_status(
    chat_handler: object,
) -> None:
    """Handler streams long response and finalizes status."""
    message = Message()

    async def process(kwargs: object) -> str:
        await kwargs["on_update"]("A" * 300)
        await asyncio.sleep(0.81)
        await kwargs["on_update"]("B" * 300)
        return "Итоговый ответ"

    chat_handler._test_pipeline.process = process

    await chat_handler.handle_message(message)

    # First status is edited once during streaming and once for final delivery.
    assert len(chat_handler._test_safe_edits) == 2
    assert chat_handler._test_safe_edits[-1][1] == "Итоговый ответ"
    assert message.answers == [("A" * 300, {"parse_mode": "HTML"})]
    assert chat_handler._test_typing_stopped.is_set()


@pytest.mark.asyncio
async def test_handler_cancellation_updates_status_and_cleans_typing_task(
    chat_handler: object,
) -> None:
    """Handler cancellation updates status and cleans typing task."""
    message = Message()

    async def process(kwargs: object) -> None:
        await kwargs["on_update"]("X" * 300)
        raise asyncio.CancelledError

    chat_handler._test_pipeline.process = process

    with pytest.raises(asyncio.CancelledError):
        await chat_handler.handle_message(message)

    assert chat_handler._test_safe_edits[-1][1] == "⏹ Запрос отменён."
    assert chat_handler._test_typing_started.is_set()
    assert chat_handler._test_typing_stopped.is_set()
    assert chat_handler._test_calls[-1] == "lock-exit"


@pytest.mark.asyncio
async def test_handler_returns_early_for_aggregated_continuation(
    chat_handler: object,
) -> None:
    """Handler returns early for aggregated continuation."""
    message = Message()
    chat_handler._test_aggregator.result = None

    await chat_handler.handle_message(message)

    assert chat_handler._test_calls == ["log", "inspect", "aggregate"]
    assert not chat_handler._test_lock_entered.is_set()
    assert message.answers == []


@pytest.mark.asyncio
async def test_handler_rejects_user_when_pending_request_limit_is_reached(
    chat_handler: object,
) -> None:
    """Handler rejects user when pending request limit is reached."""
    message = Message()
    handler_module = importlib.import_module("bot.handlers.chat.handler")
    handler_module.pending_requests = lambda _user_id: 3

    await chat_handler.handle_message(message)

    assert message.answers == [
        ("⏳ Я ещё обрабатываю твои предыдущие сообщения. Подожди немного.", {})
    ]
    assert "lock-enter" not in chat_handler._test_calls
    assert not chat_handler._test_typing_started.is_set()


@pytest.mark.asyncio
async def test_handler_routes_processing_error_to_central_error_handler(
    chat_handler: object,
) -> None:
    """Handler routes processing error to central error handler."""
    message = Message()

    async def process(_kwargs: object) -> None:
        msg = "pipeline failed"
        raise RuntimeError(msg)

    chat_handler._test_pipeline.process = process

    await chat_handler.handle_message(message)

    assert len(chat_handler._test_error_calls) == 1
    error = chat_handler._test_error_calls[0]
    assert error["message"] is message
    assert error["user_id"] == 7
    assert isinstance(error["error"], RuntimeError)
    assert chat_handler._test_typing_stopped.is_set()


@pytest.mark.asyncio
async def test_handler_preserves_final_answer_after_stream_edit_failure(
    chat_handler: object,
) -> None:
    """Handler preserves final answer after stream edit failure."""
    message = Message()

    async def broken_edit(_status: object, _text: str) -> None:
        msg = "telegram edit failed"
        raise RuntimeError(msg)

    handler_module = importlib.import_module("bot.handlers.chat.handler")
    handler_module.safe_edit = broken_edit

    async def process(kwargs: object) -> str:
        await kwargs["on_update"]("A" * 300)
        await asyncio.sleep(0.81)
        await kwargs["on_update"]("B" * 300)
        return "Финальный ответ не должен потеряться"

    chat_handler._test_pipeline.process = process

    await chat_handler.handle_message(message)

    # Первый answer создаёт stream-status; fallback отправляет полный ответ.
    assert message.answers == [
        ("A" * 300, {"parse_mode": "HTML"}),
        ("Финальный ответ не должен потеряться", {"parse_mode": "HTML"}),
    ]
    assert chat_handler._test_typing_stopped.is_set()


@pytest.mark.asyncio
async def test_handler_routes_llm_connection_loss_with_existing_status(
    chat_handler: object,
) -> None:
    """Handler routes llm connection loss with existing status."""
    message = Message()

    async def process(kwargs: object) -> None:
        await kwargs["on_update"]("S" * 300)
        msg = "llama-server stopped"
        raise ConnectionError(msg)

    chat_handler._test_pipeline.process = process

    await chat_handler.handle_message(message)

    assert len(chat_handler._test_error_calls) == 1
    error = chat_handler._test_error_calls[0]
    assert error["message"] is message
    assert error["status"].text == "S" * 300
    assert isinstance(error["error"], ConnectionError)
    assert chat_handler._test_typing_stopped.is_set()
