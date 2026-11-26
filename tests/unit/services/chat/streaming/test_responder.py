# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for streaming responder."""

import asyncio
import logging
from collections.abc import Awaitable, Callable

import pytest

from bot_obormot.services.chat.reply import ReplyTarget
from bot_obormot.services.chat.streaming.responder import (
    StreamingResponder,
    StreamingResponderOptions,
)
from tests.support.chat_streaming import (
    FakeMessage,
    FakeReplyMessage,
    edit_status,
    single_answer,
    split_text,
)

TokenCounter = Callable[[str], Awaitable[int]]
StatusEditor = Callable[..., Awaitable[None]]


def _responder(
    message: object | None = None,
    *,
    count: TokenCounter | None = None,
    safe_edit: StatusEditor | None = None,
    token_threshold: int = 150,
    update_interval: int = 0,
) -> StreamingResponder:
    async def default_count(_text: str) -> int:
        return 151

    async def default_edit(
        _message: object,
        _text: str,
        **_kwargs: object,
    ) -> None:
        return None

    return StreamingResponder(
        message=message or FakeMessage(),
        user_id=42,
        count_text_tokens=count or default_count,
        safe_edit=safe_edit or default_edit,
        options=StreamingResponderOptions(
            splitter=split_text,
            token_threshold=token_threshold,
            update_interval=update_interval,
            max_message_length=3900,
        ),
    )


def _recording_count(calls: list[str], tokens: int) -> TokenCounter:
    """Return a token counter that records each text and returns ``tokens``."""

    async def count(text: str) -> int:
        calls.append(text)
        return tokens

    return count


def _flaky_count(calls: list[str]) -> TokenCounter:
    """Return a token counter that fails on its first call only."""

    async def count(text: str) -> int:
        calls.append(text)
        if len(calls) == 1:
            msg = "tokenizer down"
            raise RuntimeError(msg)
        return 151

    return count


def _recording_edit(edits: list[tuple[object, str]]) -> StatusEditor:
    """Return a status editor that records each edit."""

    async def safe_edit(status: object, text: str, **_kwargs: object) -> None:
        edits.append((status, text))

    return safe_edit


async def _broken_edit(_status: object, _text: str, **_kwargs: object) -> None:
    msg = "edit failed"
    raise RuntimeError(msg)


@pytest.mark.asyncio
async def test_responder_skips_token_count_before_initial_checkpoint() -> None:
    calls: list[str] = []
    responder = _responder(count=_recording_count(calls, 151))
    await responder.on_update("q" * 299)
    expected_empty: list[str] = []
    assert calls == expected_empty, "tokens were counted before 300 characters"


@pytest.mark.asyncio
async def test_responder_sends_nothing_before_initial_checkpoint() -> None:
    message = FakeMessage()
    responder = _responder(message)
    await responder.on_update("w" * 299)
    expected_empty: list[tuple[str, dict[str, object]]] = []
    assert message.answers == expected_empty, "a status was sent too early"


@pytest.mark.asyncio
async def test_responder_keeps_initial_checkpoint_before_it_is_reached() -> None:
    responder = _responder()
    await responder.on_update("e" * 299)
    expected_next_token_check_chars = 300
    assert responder.next_token_check_chars == expected_next_token_check_chars, (
        "the initial character checkpoint moved"
    )


@pytest.mark.asyncio
async def test_responder_counts_tokens_at_initial_checkpoint() -> None:
    calls: list[str] = []
    responder = _responder(count=_recording_count(calls, 151))
    text = "r" * 300
    await responder.on_update(text)
    expected_calls = [text]
    assert calls == expected_calls, "tokens were not counted at 300 characters"


@pytest.mark.asyncio
async def test_responder_sends_status_after_long_token_count() -> None:
    message = FakeMessage()
    responder = _responder(message)
    text = "t" * 300
    await responder.on_update(text)
    expected_answers: list[tuple[str, dict[str, object]]] = [(text, {})]
    assert message.answers == expected_answers, "the status message was not sent"


@pytest.mark.asyncio
async def test_responder_stores_status_after_long_token_count() -> None:
    responder = _responder()
    text = "y" * 300
    await responder.on_update(text)
    status_text = getattr(responder.status, "text", None)
    assert status_text == text, "the status message was not stored"


@pytest.mark.asyncio
async def test_responder_remembers_displayed_text_after_creating_status() -> None:
    responder = _responder()
    text = "u" * 300
    await responder.on_update(text)
    assert responder.last_displayed_text == text, "the displayed text was not stored"


@pytest.mark.asyncio
async def test_responder_moves_checkpoint_after_counting_tokens() -> None:
    responder = _responder()
    await responder.on_update("i" * 300)
    expected_next_token_check_chars = 428
    assert responder.next_token_check_chars == expected_next_token_check_chars, (
        "the checkpoint did not move by 128 characters"
    )


@pytest.mark.asyncio
async def test_responder_skips_token_count_before_next_checkpoint() -> None:
    calls: list[str] = []
    responder = _responder(count=_recording_count(calls, 150))
    await responder.on_update("o" * 300)
    await responder.on_update("p" * 427)
    expected_count = 1
    assert len(calls) == expected_count, "tokens were counted before 428 characters"


@pytest.mark.asyncio
async def test_responder_creates_no_status_after_short_token_count() -> None:
    responder = _responder(count=_recording_count([], 150))
    await responder.on_update("a" * 300)
    await responder.on_update("s" * 427)
    assert responder.status is None, "a status was created for a short answer"


@pytest.mark.asyncio
async def test_responder_counts_tokens_again_at_next_checkpoint() -> None:
    calls: list[str] = []
    responder = _responder(count=_recording_count(calls, 150))
    await responder.on_update("d" * 300)
    await responder.on_update("f" * 427)
    await responder.on_update("g" * 428)
    expected_count = 2
    assert len(calls) == expected_count, "tokens were not counted at 428 characters"


@pytest.mark.asyncio
async def test_responder_moves_checkpoint_again_after_short_token_count() -> None:
    responder = _responder(count=_recording_count([], 150))
    await responder.on_update("h" * 300)
    await responder.on_update("j" * 427)
    await responder.on_update("k" * 428)
    expected_next_token_check_chars = 556
    assert responder.next_token_check_chars == expected_next_token_check_chars, (
        "the checkpoint did not move after the second count"
    )


@pytest.mark.asyncio
async def test_responder_creates_no_status_after_second_short_token_count() -> None:
    responder = _responder(count=_recording_count([], 150))
    await responder.on_update("l" * 300)
    await responder.on_update("z" * 427)
    await responder.on_update("c" * 428)
    assert responder.status is None, "a status was created for a short answer"


@pytest.mark.asyncio
async def test_responder_skips_edit_when_chunk_is_unchanged() -> None:
    edits: list[tuple[object, str]] = []
    responder = _responder(safe_edit=_recording_edit(edits))
    text = "first" + "v" * 295
    await responder.on_update(text)
    await responder.on_update(text)
    expected_empty: list[tuple[object, str]] = []
    assert edits == expected_empty, "an unchanged chunk was edited"


@pytest.mark.asyncio
async def test_responder_edits_status_when_chunk_changes() -> None:
    edits: list[tuple[object, str]] = []
    responder = _responder(safe_edit=_recording_edit(edits))
    await responder.on_update("first" + "b" * 295)
    status = responder.status
    changed_text = "second" + "n" * 294
    await responder.on_update(changed_text)
    expected_edits = [(status, changed_text)]
    assert edits == expected_edits, "the changed chunk was not edited"


@pytest.mark.asyncio
async def test_responder_remembers_edited_text() -> None:
    responder = _responder()
    await responder.on_update("начало" + "m" * 294)
    changed_text = "продолжение" + "m" * 289
    await responder.on_update(changed_text)
    assert responder.last_displayed_text == changed_text, (
        "the edited text was not stored"
    )


@pytest.mark.asyncio
async def test_responder_keeps_streaming_after_count_failure() -> None:
    responder = _responder(count=_flaky_count([]))
    await responder.on_update("Q" * 300)
    assert responder.streaming_failed is False, "a count failure disabled streaming"


@pytest.mark.asyncio
async def test_responder_counts_again_after_count_failure() -> None:
    calls: list[str] = []
    responder = _responder(count=_flaky_count(calls))
    await responder.on_update("W" * 300)
    await responder.on_update("E" * 427)
    await responder.on_update("R" * 428)
    expected_attempts = 2
    assert len(calls) == expected_attempts, "the count was not retried"


@pytest.mark.asyncio
async def test_responder_creates_status_after_count_recovers() -> None:
    responder = _responder(count=_flaky_count([]))
    await responder.on_update("T" * 300)
    await responder.on_update("Y" * 427)
    await responder.on_update("U" * 428)
    assert responder.status is not None, "no status after the count recovered"


@pytest.mark.asyncio
async def test_responder_warns_about_count_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responder = _responder(count=_flaky_count([]))
    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await responder.on_update("I" * 300)
    warning_text = "Could not count streaming tokens"
    assert warning_text in caplog.text, "the count failure was not logged"


@pytest.mark.asyncio
async def test_responder_disables_streaming_after_initial_send_failure() -> None:
    failures: list[Exception | None] = [RuntimeError("telegram down")] * 2
    responder = _responder(FakeReplyMessage(failures=failures))
    await responder.on_update("O" * 300)
    await responder.on_update("P" * 500)
    assert responder.streaming_failed is True, "a send failure kept streaming on"


@pytest.mark.asyncio
async def test_responder_keeps_no_status_after_initial_send_failure() -> None:
    failures: list[Exception | None] = [RuntimeError("сеть недоступна")] * 2
    responder = _responder(FakeReplyMessage(failures=failures))
    await responder.on_update("A" * 300)
    await responder.on_update("S" * 500)
    assert responder.status is None, "a status exists after a send failure"


@pytest.mark.asyncio
async def test_responder_warns_about_initial_send_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    failures: list[Exception | None] = [RuntimeError("gateway timeout")] * 2
    responder = _responder(FakeReplyMessage(failures=failures))
    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await responder.on_update("D" * 300)
        await responder.on_update("F" * 500)
    warning_text = "Could not start streaming display"
    assert warning_text in caplog.text, "the send failure was not logged"


@pytest.mark.asyncio
async def test_responder_disables_streaming_after_edit_failure() -> None:
    responder = _responder(safe_edit=_broken_edit)
    await responder.on_update("G" * 300)
    await responder.on_update("H" * 500)
    await responder.on_update("J" * 700)
    assert responder.streaming_failed is True, "an edit failure kept streaming on"


@pytest.mark.asyncio
async def test_responder_warns_about_edit_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    responder = _responder(safe_edit=_broken_edit)
    await responder.on_update("K" * 300)
    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await responder.on_update("L" * 500)
        await responder.on_update("Z" * 700)
    warning_text = "Streaming message update failed"
    assert warning_text in caplog.text, "the edit failure was not logged"


@pytest.mark.asyncio
async def test_responder_cancel_waits_for_shielded_safe_edit() -> None:
    completed = asyncio.Event()

    async def safe_edit(_status: object, _text: str, **_kwargs: object) -> None:
        await asyncio.sleep(0)
        completed.set()

    responder = _responder(safe_edit=safe_edit)
    await responder.on_update("X" * 300)
    await responder.cancel()
    assert completed.is_set(), "cancel did not wait for the status edit"


@pytest.mark.asyncio
async def test_responder_cancel_shows_cancellation_text() -> None:
    edits: list[tuple[object, str]] = []
    responder = _responder(safe_edit=_recording_edit(edits))
    await responder.on_update("C" * 300)
    status = responder.status
    await responder.cancel()
    expected_edits = [(status, "⏹ Запрос отменён.")]
    assert edits == expected_edits, "cancel did not show the cancellation text"


@pytest.mark.asyncio
async def test_streaming_message_is_created_as_a_reply() -> None:
    message = FakeReplyMessage()
    reply_message_id = 42
    responder = StreamingResponder(
        message,
        9,
        _recording_count([], 999),
        edit_status,
        reply_to=ReplyTarget(chat_id=5, message_id=reply_message_id),
    )
    await responder.on_update("V" * 400)
    _, kwargs = single_answer(message)
    message_id = getattr(kwargs["reply_parameters"], "message_id", None)
    assert message_id == reply_message_id, "the status is not a reply"


@pytest.mark.asyncio
async def test_streaming_message_is_created_without_parse_mode() -> None:
    message = FakeReplyMessage()
    responder = StreamingResponder(
        message,
        17,
        _recording_count([], 640),
        edit_status,
        reply_to=ReplyTarget(chat_id=8, message_id=73),
    )
    await responder.on_update("B" * 450)
    _, kwargs = single_answer(message)
    parse_mode_field = "parse_mode"
    assert parse_mode_field not in kwargs, "the status was sent with a parse mode"
