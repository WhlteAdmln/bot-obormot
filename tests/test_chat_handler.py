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
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest


@pytest.fixture
def chat_handler(monkeypatch):
    def module(name, **attributes):
        result = types.ModuleType(name)
        for key, value in attributes.items():
            setattr(result, key, value)
        monkeypatch.setitem(sys.modules, name, result)
        return result

    class Router:
        def message(self, *_args, **_kwargs):
            return lambda function: function

    aiogram = module("aiogram", Router=Router)
    module("aiogram.types", Message=object)

    calls = []
    typing_started = asyncio.Event()
    typing_stopped = asyncio.Event()
    lock_entered = asyncio.Event()

    class Aggregator:
        result = "входящий текст"

        async def collect(self, _message):
            calls.append("aggregate")
            return self.result

    aggregator = Aggregator()

    def log_incoming(_message):
        calls.append("log")

    def inspect(_message):
        calls.append("inspect")
        return SimpleNamespace(
            has_content=True,
            has_text=True,
            has_media=False,
            has_audio=False,
            has_document=False,
        )

    async def prepare(_message, _info, text_override=None):
        calls.append(("prepare", text_override))
        await asyncio.sleep(0)
        return SimpleNamespace(
            user_content="prepared user content",
            saved_user_text="saved user text",
            image_bytes=None,
        )

    @asynccontextmanager
    async def user_lock(_user_id):
        calls.append("lock-enter")
        lock_entered.set()
        try:
            yield
        finally:
            calls.append("lock-exit")

    async def keep_typing(_message):
        typing_started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            typing_stopped.set()
            raise

    safe_edits = []

    async def safe_edit(message, text):
        safe_edits.append((message, text))

    error_calls = []

    async def handle_error(**kwargs):
        error_calls.append(kwargs)

    pipeline = SimpleNamespace()

    async def process_chat(**kwargs):
        calls.append("process")
        process = pipeline.process
        return await process(kwargs)

    pipeline.process = lambda _kwargs: None

    class FakeLLM:
        async def count_text_tokens(self, _text):
            calls.append("count-tokens")
            return 151

    module(
        "bot.services.chat.aggregation",
        message_aggregator=aggregator,
    )
    module(
        "bot.services.chat.errors.handler",
        handle_chat_error=handle_error,
    )
    module(
        "bot.services.chat.incoming_log",
        log_incoming_message=log_incoming,
    )
    module(
        "bot.services.chat.input",
        inspect_message=inspect,
        prepare_message=prepare,
    )
    module(
        "bot.services.chat.locks",
        get_user_lock=user_lock,
        pending_requests=lambda _user_id: 0,
    )
    module("bot.services.chat.pipeline", process_chat=process_chat)
    module("bot.services.chat.reporting", safe_edit=safe_edit)
    module("bot.services.telegram.chat_action", keep_typing=keep_typing)
    module("bot.services.llm", llm_client=FakeLLM())

    # Ensure a fresh package import binds the test doubles above.
    sys.modules.pop("bot.handlers.chat.handler", None)
    sys.modules.pop("bot.handlers.chat", None)
    import bot.handlers

    if hasattr(bot.handlers, "chat"):
        delattr(bot.handlers, "chat")

    package = importlib.import_module("bot.handlers.chat")
    package._test_calls = calls
    package._test_typing_started = typing_started
    package._test_typing_stopped = typing_stopped
    package._test_lock_entered = lock_entered
    package._test_safe_edits = safe_edits
    package._test_error_calls = error_calls
    package._test_pipeline = pipeline
    package._test_aggregator = aggregator
    package._test_aiogram = aiogram
    yield package

    sys.modules.pop("bot.handlers.chat.handler", None)
    sys.modules.pop("bot.handlers.chat", None)
    if hasattr(bot.handlers, "chat"):
        delattr(bot.handlers, "chat")


class Message:
    def __init__(self, text="text", user_id=7):
        self.text = text
        self.from_user = SimpleNamespace(id=user_id)
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append((text, kwargs))
        return SimpleNamespace(text=text)


@pytest.mark.asyncio
async def test_handler_preserves_order_for_short_non_streamed_response(chat_handler):
    message = Message()

    async def process(kwargs):
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
async def test_handler_streams_long_response_and_finalizes_status(chat_handler):
    message = Message()

    async def process(kwargs):
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
async def test_handler_cancellation_updates_status_and_cleans_typing_task(chat_handler):
    message = Message()

    async def process(kwargs):
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
async def test_handler_returns_early_for_aggregated_continuation(chat_handler):
    message = Message()
    chat_handler._test_aggregator.result = None

    await chat_handler.handle_message(message)

    assert chat_handler._test_calls == ["log", "inspect", "aggregate"]
    assert not chat_handler._test_lock_entered.is_set()
    assert message.answers == []


@pytest.mark.asyncio
async def test_handler_rejects_user_when_pending_request_limit_is_reached(chat_handler):
    message = Message()
    handler_module = importlib.import_module("bot.handlers.chat.handler")
    handler_module.pending_requests = lambda user_id: 3

    await chat_handler.handle_message(message)

    assert message.answers == [
        ("⏳ Я ещё обрабатываю твои предыдущие сообщения. Подожди немного.", {})
    ]
    assert "lock-enter" not in chat_handler._test_calls
    assert not chat_handler._test_typing_started.is_set()


@pytest.mark.asyncio
async def test_handler_routes_processing_error_to_central_error_handler(chat_handler):
    message = Message()

    async def process(_kwargs):
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
async def test_handler_preserves_final_answer_after_stream_edit_failure(chat_handler):
    message = Message()

    async def broken_edit(_status, _text):
        msg = "telegram edit failed"
        raise RuntimeError(msg)

    handler_module = importlib.import_module("bot.handlers.chat.handler")
    handler_module.safe_edit = broken_edit

    async def process(kwargs):
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
async def test_handler_routes_llm_connection_loss_with_existing_status(chat_handler):
    message = Message()

    async def process(kwargs):
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
