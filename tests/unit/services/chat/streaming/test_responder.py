# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for streaming responder."""

import asyncio
import logging

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
    split_text,
)


def _responder(
    message: object | None = None,
    *,
    count: object | None = None,
    safe_edit: object | None = None,
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


@pytest.mark.asyncio
async def test_responder_waits_until_initial_character_checkpoint() -> None:
    """Responder waits until initial character checkpoint."""
    calls = []

    async def count(text: str) -> int:
        calls.append(text)
        return 151

    message = FakeMessage()
    responder = _responder(message, count=count)

    await responder.on_update("x" * 299)

    assert calls == []
    assert message.answers == []
    assert responder.next_token_check_chars == 300


@pytest.mark.asyncio
async def test_responder_checks_token_count_at_threshold_and_creates_status() -> None:
    """Responder checks token count at threshold and creates status."""
    calls = []
    message = FakeMessage()

    async def count(text: str) -> int:
        calls.append(text)
        return 151

    responder = _responder(message, count=count)
    text = "x" * 300
    await responder.on_update(text)

    assert calls == [text]
    assert message.answers == [(text, {})]
    assert responder.status.text == text
    assert responder.last_displayed_text == text
    assert responder.next_token_check_chars == 428


@pytest.mark.asyncio
async def test_responder_increases_character_checkpoint_after_short_token_count() -> (
    None
):
    """Responder increases character checkpoint after short token count."""
    calls = []
    message = FakeMessage()

    async def count(text: str) -> int:
        calls.append(text)
        return 150

    responder = _responder(message, count=count)
    await responder.on_update("a" * 300)
    await responder.on_update("b" * 427)
    assert len(calls) == 1
    assert responder.status is None

    await responder.on_update("c" * 428)
    assert len(calls) == 2
    assert responder.next_token_check_chars == 556
    assert responder.status is None


@pytest.mark.asyncio
async def test_responder_updates_status_after_interval_only_when_chunk_changes() -> (
    None
):
    """Responder updates status after interval only when chunk changes."""
    edits = []

    async def safe_edit(
        status: object,
        text: str,
        **_kwargs: object,
    ) -> None:
        edits.append((status, text))

    message = FakeMessage()
    responder = _responder(message, safe_edit=safe_edit)
    await responder.on_update("first" + "x" * 295)
    status = responder.status

    await responder.on_update("first" + "x" * 295)
    assert edits == []

    await responder.on_update("second" + "x" * 294)
    assert edits == [(status, "second" + "x" * 294)]
    assert responder.last_displayed_text == "second" + "x" * 294


@pytest.mark.asyncio
async def test_responder_count_failure_does_not_disable_future_streaming(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Responder count failure does not disable future streaming."""
    attempts = 0
    message = FakeMessage()

    async def count(_text: str) -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            msg = "tokenizer down"
            raise RuntimeError(msg)
        return 151

    responder = _responder(message, count=count)
    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await responder.on_update("a" * 300)
        assert responder.streaming_failed is False
        await responder.on_update("b" * 427)
        await responder.on_update("c" * 428)

    assert attempts == 2
    assert responder.status is not None
    assert "Could not count streaming tokens" in caplog.text


@pytest.mark.asyncio
async def test_responder_disables_streaming_after_initial_send_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Responder disables streaming after initial send failure."""

    class BrokenMessage:
        async def answer(self, *_args: object, **_kwargs: object) -> None:
            msg = "telegram down"
            raise RuntimeError(msg)

    responder = _responder(BrokenMessage())
    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await responder.on_update("x" * 300)
        await responder.on_update("y" * 500)

    assert responder.streaming_failed is True
    assert responder.status is None
    assert "Could not start streaming display" in caplog.text


@pytest.mark.asyncio
async def test_responder_disables_streaming_after_edit_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Responder disables streaming after edit failure."""

    async def broken_edit(
        _status: object,
        _text: str,
        **_kwargs: object,
    ) -> None:
        msg = "edit failed"
        raise RuntimeError(msg)

    responder = _responder(safe_edit=broken_edit)
    await responder.on_update("x" * 300)

    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await responder.on_update("y" * 500)
        await responder.on_update("z" * 700)

    assert responder.streaming_failed is True
    assert "Streaming message update failed" in caplog.text


@pytest.mark.asyncio
async def test_responder_cancel_uses_shielded_safe_edit() -> None:
    """Responder cancel uses shielded safe edit."""
    edits = []
    completed = asyncio.Event()

    async def safe_edit(
        status: object,
        text: str,
        **_kwargs: object,
    ) -> None:
        edits.append((status, text))
        await asyncio.sleep(0)
        completed.set()

    responder = _responder(safe_edit=safe_edit)
    await responder.on_update("x" * 300)
    status = responder.status

    await responder.cancel()

    assert completed.is_set()
    assert edits == [(status, "⏹ Запрос отменён.")]


@pytest.mark.asyncio
async def test_streaming_message_is_created_as_a_reply_without_parse_mode() -> None:
    """Create the streaming message as a reply and show raw text."""
    message = FakeReplyMessage()

    async def count_tokens(_text: str) -> int:
        return 999

    responder = StreamingResponder(
        message,
        9,
        count_tokens,
        edit_status,
        reply_to=ReplyTarget(chat_id=5, message_id=42),
    )

    await responder.on_update("a" * 400)

    ((_, kwargs),) = message.answers
    assert kwargs["reply_parameters"].message_id == 42
    assert "parse_mode" not in kwargs
