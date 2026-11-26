# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Characterization tests for the package-based chat handler.

The handler dependencies are replaced on the real handler module so these
tests focus on ordering, stream lifecycle, cancellation, and task cleanup
without requiring a running Telegram/LLM service.
"""

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import pytest

from bot_obormot.handlers.chat import handler as handler_module
from bot_obormot.services.chat.aggregation import AggregatedText
from bot_obormot.services.media import MediaSlots
from bot_obormot.services.telegram import TelegramDownloader
from bot_obormot.settings import Settings
from tests.support.chat_handler import (
    RecordingAggregator,
    RecordingTokenCounter,
    RecordingUserLocks,
)
from tests.support.chat_streaming import single_answer
from tests.support.settings import make_settings


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
            media_slots=MediaSlots(),
        ),
        llm_client=RecordingTokenCounter(calls),
        database=object(),
        settings=make_settings(),
        prepare_args=[],
        process_kwargs=[],
    )


def _patch_input_stubs(
    monkeypatch: pytest.MonkeyPatch,
    state: SimpleNamespace,
) -> None:
    calls = state.calls

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
        media_slots: object,
    ) -> SimpleNamespace:
        state.prepare_args.extend([downloader, media_slots, settings])
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
        state.process_kwargs.append(kwargs)
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
    _patch_input_stubs(monkeypatch, result)
    _patch_typing_stub(monkeypatch, result.typing_started, result.typing_stopped)
    _patch_processing_stubs(monkeypatch, result)
    _patch_reporting_stubs(monkeypatch, result)
    return result


class Message:
    """Message."""

    def __init__(
        self,
        text: str = "Как дела, бот?",
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


async def _handle(state: SimpleNamespace, message: Message) -> None:
    """Run the handler with the recorded collaborators of the state."""
    await handler_module.handle_message(
        message,
        llm_client=state.llm_client,
        database=state.database,
        chat_runtime=state.chat_runtime,
        settings=state.settings,
    )


async def _answer_short(state: SimpleNamespace, message: Message, answer: str) -> None:
    """Handle a message whose pipeline returns a short answer without streaming."""

    async def process(_kwargs: object) -> str:
        return answer

    state.pipeline.process = process
    await _handle(state, message)


async def _answer_streamed(
    state: SimpleNamespace, message: Message, final: str
) -> None:
    """Handle a message whose pipeline streams two long updates, then answers."""

    async def process(kwargs: dict[str, Callable[[str], Awaitable[None]]]) -> str:
        await kwargs["on_update"]("A" * 300)
        await asyncio.sleep(0.81)
        await kwargs["on_update"]("B" * 300)
        return final

    state.pipeline.process = process
    await _handle(state, message)


async def _cancel_after_update(state: SimpleNamespace, message: Message) -> None:
    """Handle a message whose pipeline streams once and is then cancelled."""

    async def process(kwargs: dict[str, Callable[[str], Awaitable[None]]]) -> None:
        await kwargs["on_update"]("X" * 300)
        raise asyncio.CancelledError

    state.pipeline.process = process
    with pytest.raises(asyncio.CancelledError):
        await _handle(state, message)


async def _fail_processing(state: SimpleNamespace, message: Message) -> None:
    """Handle a message whose pipeline fails before any update."""

    async def process(_kwargs: object) -> None:
        msg = "pipeline failed"
        raise RuntimeError(msg)

    state.pipeline.process = process
    await _handle(state, message)


async def _lose_llm_connection(state: SimpleNamespace, message: Message) -> None:
    """Handle a message whose LLM connection breaks after one streamed update."""

    async def process(kwargs: dict[str, Callable[[str], Awaitable[None]]]) -> None:
        await kwargs["on_update"]("S" * 300)
        msg = "llama-server stopped"
        raise ConnectionError(msg)

    state.pipeline.process = process
    await _handle(state, message)


async def _break_stream_edits(
    state: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
    message: Message,
    final: str,
) -> None:
    """Handle a streamed answer while every status edit fails."""

    async def broken_edit(_status: object, _text: str, **_kwargs: object) -> None:
        msg = "telegram edit failed"
        raise RuntimeError(msg)

    monkeypatch.setattr(handler_module, "safe_edit", broken_edit)
    await _answer_streamed(state, message, final)


@pytest.mark.asyncio
async def test_handler_passes_user_id_to_processing(state: SimpleNamespace) -> None:
    user_id = 7
    await _answer_short(state, Message(user_id=user_id), "ответ про id")
    received = state.process_kwargs[0]["user_id"]
    assert received == user_id, "processing got another user id"


@pytest.mark.asyncio
async def test_handler_passes_prepared_content_to_processing(
    state: SimpleNamespace,
) -> None:
    expected_user_content = "prepared user content"
    await _answer_short(state, Message(text="контент"), "ответ про контент")
    received = state.process_kwargs[0]["user_content"]
    assert received == expected_user_content, "processing got unprepared content"


@pytest.mark.asyncio
async def test_handler_passes_runtime_and_settings_to_prepare_message(
    state: SimpleNamespace,
) -> None:
    runtime = state.chat_runtime
    expected = [id(runtime.downloader), id(runtime.media_slots), id(state.settings)]
    await _answer_short(state, Message(text="подготовка"), "ответ о подготовке")
    received = [id(argument) for argument in state.prepare_args]
    assert received == expected, "prepare_message got other collaborators"


@pytest.mark.asyncio
async def test_router_handler_passes_given_runtime_to_prepare_message(
    state: SimpleNamespace,
) -> None:
    runtime = state.chat_runtime
    expected = [id(runtime.downloader), id(runtime.media_slots)]
    router = handler_module.create_router(runtime)
    callback = router.message.handlers[0].callback
    await callback(
        Message(text="через роутер", user_id=58),
        llm_client=state.llm_client,
        database=state.database,
        settings=state.settings,
    )
    received = [id(argument) for argument in state.prepare_args[:2]]
    assert received == expected, "the router handler got another runtime"


@pytest.mark.asyncio
async def test_handler_sends_short_answer_without_streaming(
    state: SimpleNamespace,
) -> None:
    answer = "короткий ответ"
    expected_answers: list[tuple[str, dict[str, object]]] = [(answer, {})]
    message = Message()
    await _answer_short(state, message, answer)
    assert message.answers == expected_answers, "the short answer was not sent once"


@pytest.mark.asyncio
async def test_handler_preserves_order_before_preparing_the_message(
    state: SimpleNamespace,
) -> None:
    expected_calls = [
        "log",
        "inspect",
        "aggregate",
        "lock-enter",
        ("prepare", "входящий текст"),
    ]
    await _answer_short(state, Message(user_id=31), "порядок")
    assert state.calls[:5] == expected_calls, "steps before preparing are reordered"


@pytest.mark.asyncio
async def test_handler_processes_after_preparing_the_message(
    state: SimpleNamespace,
) -> None:
    prepare_call = ("prepare", "входящий текст")
    await _answer_short(state, Message(user_id=44), "после подготовки")
    process_index = state.calls.index("process")
    prepare_index = state.calls.index(prepare_call)
    assert process_index > prepare_index, "processing ran before preparing"


@pytest.mark.asyncio
async def test_handler_starts_typing_for_short_answer(state: SimpleNamespace) -> None:
    await _answer_short(state, Message(user_id=52), "печатает")
    assert state.typing_started.is_set(), "the typing indicator did not start"


@pytest.mark.asyncio
async def test_handler_stops_typing_after_short_answer(state: SimpleNamespace) -> None:
    await _answer_short(state, Message(user_id=63), "перестал печатать")
    assert state.typing_stopped.is_set(), "the typing indicator kept running"


@pytest.mark.asyncio
async def test_handler_releases_user_lock_last_after_short_answer(
    state: SimpleNamespace,
) -> None:
    expected_last_call = "lock-exit"
    await _answer_short(state, Message(user_id=78), "замок")
    assert state.calls[-1] == expected_last_call, "the user lock was not released last"


@pytest.mark.asyncio
async def test_handler_edits_status_for_stream_update_and_final_answer(
    state: SimpleNamespace,
) -> None:
    expected_count = 2
    await _answer_streamed(state, Message(user_id=81), "Итоговый ответ")
    assert len(state.safe_edits) == expected_count, "status edits were not throttled"


@pytest.mark.asyncio
async def test_handler_finalizes_streamed_status_with_final_answer(
    state: SimpleNamespace,
) -> None:
    final = "Итоговый ответ"
    await _answer_streamed(state, Message(user_id=82), final)
    assert state.safe_edits[-1][1] == final, "the status does not show the final answer"


@pytest.mark.asyncio
async def test_handler_sends_first_stream_update_as_status_message(
    state: SimpleNamespace,
) -> None:
    expected_answers: list[tuple[str, dict[str, object]]] = [("A" * 300, {})]
    message = Message(user_id=83)
    await _answer_streamed(state, message, "Окончательно")
    assert message.answers == expected_answers, "the status message was not sent once"


@pytest.mark.asyncio
async def test_handler_stops_typing_after_streamed_answer(
    state: SimpleNamespace,
) -> None:
    await _answer_streamed(state, Message(user_id=84), "Стрим закончен")
    assert state.typing_stopped.is_set(), "the typing indicator kept running"


@pytest.mark.asyncio
async def test_handler_cancellation_updates_status(state: SimpleNamespace) -> None:
    expected_status = "⏹ Запрос отменён."
    await _cancel_after_update(state, Message(user_id=91))
    assert state.safe_edits[-1][1] == expected_status, "the status was not updated"


@pytest.mark.asyncio
async def test_handler_cancellation_happens_after_typing_started(
    state: SimpleNamespace,
) -> None:
    await _cancel_after_update(state, Message(user_id=92))
    assert state.typing_started.is_set(), "the typing indicator did not start"


@pytest.mark.asyncio
async def test_handler_cancellation_cleans_typing_task(state: SimpleNamespace) -> None:
    await _cancel_after_update(state, Message(user_id=93))
    assert state.typing_stopped.is_set(), "the typing task was not cancelled"


@pytest.mark.asyncio
async def test_handler_cancellation_releases_user_lock_last(
    state: SimpleNamespace,
) -> None:
    expected_last_call = "lock-exit"
    await _cancel_after_update(state, Message(user_id=94))
    assert state.calls[-1] == expected_last_call, "the user lock was not released last"


@pytest.mark.asyncio
async def test_handler_stops_after_aggregating_a_continuation(
    state: SimpleNamespace,
) -> None:
    expected_calls = ["log", "inspect", "aggregate"]
    state.aggregator.result = None
    await _handle(state, Message(text="продолжение"))
    assert state.calls == expected_calls, "the handler went on after aggregation"


@pytest.mark.asyncio
async def test_handler_does_not_lock_user_for_aggregated_continuation(
    state: SimpleNamespace,
) -> None:
    state.aggregator.result = None
    await _handle(state, Message(text="хвост сообщения"))
    assert not state.lock_entered.is_set(), "the user lock was taken"


@pytest.mark.asyncio
async def test_handler_sends_no_answer_for_aggregated_continuation(
    state: SimpleNamespace,
) -> None:
    expected_empty: list[tuple[str, dict[str, object]]] = []
    message = Message(text="ещё кусок")
    state.aggregator.result = None
    await _handle(state, message)
    assert message.answers == expected_empty, "an answer was sent for a continuation"


@pytest.mark.asyncio
async def test_handler_tells_user_to_wait_when_pending_limit_is_reached(
    state: SimpleNamespace,
) -> None:
    expected_answers: list[tuple[str, dict[str, object]]] = [
        ("⏳ Я ещё обрабатываю твои предыдущие сообщения. Подожди немного.", {})
    ]
    message = Message(user_id=101)
    state.user_locks.pending_count = 3
    await _handle(state, message)
    assert message.answers == expected_answers, "the user was not told to wait"


@pytest.mark.asyncio
async def test_handler_does_not_lock_user_when_pending_limit_is_reached(
    state: SimpleNamespace,
) -> None:
    lock_event = "lock-enter"
    state.user_locks.pending_count = 4
    await _handle(state, Message(user_id=102))
    assert lock_event not in state.calls, "the user lock was taken over the limit"


@pytest.mark.asyncio
async def test_handler_does_not_type_when_pending_limit_is_reached(
    state: SimpleNamespace,
) -> None:
    state.user_locks.pending_count = 3
    await _handle(state, Message(user_id=103))
    assert not state.typing_started.is_set(), "typing started over the limit"


@pytest.mark.asyncio
async def test_handler_routes_processing_error_to_central_handler_once(
    state: SimpleNamespace,
) -> None:
    expected_count = 1
    await _fail_processing(state, Message(user_id=111))
    assert len(state.error_calls) == expected_count, "the error was not routed once"


@pytest.mark.asyncio
async def test_handler_passes_message_to_error_handler(state: SimpleNamespace) -> None:
    message = Message(user_id=112)
    await _fail_processing(state, message)
    received = state.error_calls[0]["message"]
    assert received is message, "the error handler got another message"


@pytest.mark.asyncio
async def test_handler_passes_user_id_to_error_handler(state: SimpleNamespace) -> None:
    user_id = 113
    await _fail_processing(state, Message(user_id=user_id))
    received = state.error_calls[0]["user_id"]
    assert received == user_id, "the error handler got another user id"


@pytest.mark.asyncio
async def test_handler_passes_processing_error_to_error_handler(
    state: SimpleNamespace,
) -> None:
    await _fail_processing(state, Message(user_id=114))
    error = state.error_calls[0]["error"]
    assert isinstance(error, RuntimeError), "the error handler got another error"


@pytest.mark.asyncio
async def test_handler_stops_typing_after_processing_error(
    state: SimpleNamespace,
) -> None:
    await _fail_processing(state, Message(user_id=115))
    assert state.typing_stopped.is_set(), "the typing indicator kept running"


@pytest.mark.asyncio
async def test_handler_preserves_final_answer_after_stream_edit_failure(
    state: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final = "Финальный ответ не должен потеряться"
    expected_answers: list[tuple[str, dict[str, object]]] = [
        ("A" * 300, {}),
        (final, {}),
    ]
    message = Message(user_id=121)
    await _break_stream_edits(state, monkeypatch, message, final)
    assert message.answers == expected_answers, "the final answer was lost"


@pytest.mark.asyncio
async def test_handler_stops_typing_after_stream_edit_failure(
    state: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = Message(user_id=122)
    await _break_stream_edits(state, monkeypatch, message, "Ответ после сбоя")
    assert state.typing_stopped.is_set(), "the typing indicator kept running"


@pytest.mark.asyncio
async def test_handler_routes_llm_connection_loss_once(state: SimpleNamespace) -> None:
    expected_count = 1
    await _lose_llm_connection(state, Message(user_id=131))
    assert len(state.error_calls) == expected_count, "the error was not routed once"


@pytest.mark.asyncio
async def test_handler_passes_message_on_llm_connection_loss(
    state: SimpleNamespace,
) -> None:
    message = Message(user_id=132)
    await _lose_llm_connection(state, message)
    received = state.error_calls[0]["message"]
    assert received is message, "the error handler got another message"


@pytest.mark.asyncio
async def test_handler_passes_existing_status_on_llm_connection_loss(
    state: SimpleNamespace,
) -> None:
    expected_status_text = "S" * 300
    await _lose_llm_connection(state, Message(user_id=133))
    status_text = state.error_calls[0]["status"].text
    assert status_text == expected_status_text, "the existing status was not passed"


@pytest.mark.asyncio
async def test_handler_passes_connection_error_on_llm_connection_loss(
    state: SimpleNamespace,
) -> None:
    await _lose_llm_connection(state, Message(user_id=134))
    error = state.error_calls[0]["error"]
    assert isinstance(error, ConnectionError), "the error handler got another error"


@pytest.mark.asyncio
async def test_handler_stops_typing_after_llm_connection_loss(
    state: SimpleNamespace,
) -> None:
    await _lose_llm_connection(state, Message(user_id=135))
    assert state.typing_stopped.is_set(), "the typing indicator kept running"


@pytest.mark.asyncio
async def test_handler_sends_markdown_answer_as_markdown_v2(
    state: SimpleNamespace,
) -> None:
    expected_text = "*ответ*"
    message = Message(message_id=11)
    await _answer_short(state, message, "**ответ**")
    text, _kwargs = single_answer(message)
    assert text == expected_text, "the answer was not converted to MarkdownV2"


@pytest.mark.asyncio
async def test_handler_sets_markdown_v2_parse_mode_for_markdown_answer(
    state: SimpleNamespace,
) -> None:
    expected_parse_mode = "MarkdownV2"
    message = Message(message_id=12)
    await _answer_short(state, message, "**жирный**")
    _text, kwargs = single_answer(message)
    assert kwargs["parse_mode"] == expected_parse_mode, "the parse mode is wrong"


@pytest.mark.asyncio
async def test_handler_replies_to_the_incoming_message(
    state: SimpleNamespace,
) -> None:
    expected_message_id = 14
    message = Message(message_id=expected_message_id)
    await _answer_short(state, message, "**ответ на сообщение**")
    _text, kwargs = single_answer(message)
    reply_to = kwargs["reply_parameters"].message_id
    assert reply_to == expected_message_id, "the answer replies to another message"


@pytest.mark.asyncio
async def test_handler_allows_sending_without_reply(state: SimpleNamespace) -> None:
    message = Message(message_id=15)
    await _answer_short(state, message, "**без ответа**")
    _text, kwargs = single_answer(message)
    allowed = kwargs["reply_parameters"].allow_sending_without_reply
    assert allowed is True, "the answer fails when the original is gone"


async def _answer_aggregated(state: SimpleNamespace) -> Message:
    """Answer an aggregated text whose last part is another message."""
    first = Message(message_id=11)
    last = Message(message_id=13)
    state.aggregator.result = AggregatedText("первая\nтретья", last)
    await _answer_short(state, first, "ответ")
    return first


@pytest.mark.asyncio
async def test_handler_sends_plain_answer_for_aggregated_messages(
    state: SimpleNamespace,
) -> None:
    expected_text = "ответ"
    first = await _answer_aggregated(state)
    text, _kwargs = single_answer(first)
    assert text == expected_text, "the aggregated answer text changed"


@pytest.mark.asyncio
async def test_handler_sends_plain_answer_without_parse_mode(
    state: SimpleNamespace,
) -> None:
    parse_mode_field = "parse_mode"
    first = await _answer_aggregated(state)
    _text, kwargs = single_answer(first)
    assert parse_mode_field not in kwargs, "a plain answer got a parse mode"


@pytest.mark.asyncio
async def test_handler_replies_to_the_last_aggregated_message(
    state: SimpleNamespace,
) -> None:
    expected_message_id = 13
    first = await _answer_aggregated(state)
    _text, kwargs = single_answer(first)
    reply_to = kwargs["reply_parameters"].message_id
    assert reply_to == expected_message_id, "the answer replies to another message"
