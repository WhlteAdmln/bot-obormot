# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat streaming."""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from bot.services.chat.streaming.delivery import (
    DeliveryOptions,
    deliver_final_response,
)
from bot.services.chat.streaming.responder import (
    StreamingResponder,
    StreamingResponderOptions,
)
from bot.services.chat.streaming.settings import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
)


class FakeMessage:
    """Fake message."""

    def __init__(self) -> None:
        """Initializes the test double."""
        self.answers = []

    async def answer(self, text: str, **kwargs: object) -> SimpleNamespace:
        """Answer."""
        self.answers.append((text, kwargs))
        return SimpleNamespace(text=text)


def _split(text: str, *, max_length: object) -> list[object]:
    return [
        text[index : index + max_length] for index in range(0, len(text), max_length)
    ]


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

    async def default_edit(_message: object, _text: str) -> None:
        return None

    return StreamingResponder(
        message=message or FakeMessage(),
        user_id=42,
        count_text_tokens=count or default_count,
        safe_edit=safe_edit or default_edit,
        options=StreamingResponderOptions(
            formatter=lambda text: text,
            splitter=_split,
            token_threshold=token_threshold,
            update_interval=update_interval,
            max_message_length=3900,
        ),
    )


def test_streaming_settings_preserve_original_values() -> None:
    """Streaming settings preserve original values."""
    assert STREAM_TOKEN_THRESHOLD == 150
    assert STREAM_UPDATE_INTERVAL == 0.8
    assert MAX_MESSAGE_LENGTH == 3900


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
    assert message.answers == [(text, {"parse_mode": "HTML"})]
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

    async def safe_edit(status: object, text: str) -> None:
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
    with caplog.at_level(logging.WARNING, logger="bot.handlers.chat"):
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
    with caplog.at_level(logging.WARNING, logger="bot.handlers.chat"):
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

    async def broken_edit(_status: object, _text: str) -> None:
        msg = "edit failed"
        raise RuntimeError(msg)

    responder = _responder(safe_edit=broken_edit)
    await responder.on_update("x" * 300)

    with caplog.at_level(logging.WARNING, logger="bot.handlers.chat"):
        await responder.on_update("y" * 500)
        await responder.on_update("z" * 700)

    assert responder.streaming_failed is True
    assert "Streaming message update failed" in caplog.text


@pytest.mark.asyncio
async def test_responder_cancel_uses_shielded_safe_edit() -> None:
    """Responder cancel uses shielded safe edit."""
    edits = []
    completed = asyncio.Event()

    async def safe_edit(status: object, text: str) -> None:
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
async def test_delivery_sends_all_chunks_without_streaming_status() -> None:
    """Delivery sends all chunks without streaming status."""
    message = FakeMessage()

    await deliver_final_response(
        message=message,
        response="abcdefgh",
        status=None,
        safe_edit=lambda *_args: None,
        options=DeliveryOptions(
            formatter=lambda text: text,
            splitter=_split,
            max_message_length=3,
        ),
    )

    assert message.answers == [
        ("abc", {"parse_mode": "HTML"}),
        ("def", {"parse_mode": "HTML"}),
        ("gh", {"parse_mode": "HTML"}),
    ]


@pytest.mark.asyncio
async def test_delivery_edits_first_chunk_and_sends_remaining_chunks() -> None:
    """Delivery edits first chunk and sends remaining chunks."""
    message = FakeMessage()
    edits = []

    async def safe_edit(status: object, text: str) -> None:
        edits.append((status, text))

    status = object()
    await deliver_final_response(
        message=message,
        response="abcdefgh",
        status=status,
        safe_edit=safe_edit,
        options=DeliveryOptions(
            formatter=lambda text: text,
            splitter=_split,
            max_message_length=3,
            user_id=42,
        ),
    )

    assert edits == [(status, "abc")]
    assert message.answers == [
        ("def", {"parse_mode": "HTML"}),
        ("gh", {"parse_mode": "HTML"}),
    ]


@pytest.mark.asyncio
async def test_delivery_falls_back_to_all_chunks_when_status_edit_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Delivery falls back to all chunks when status edit fails."""
    message = FakeMessage()

    async def broken_edit(_status: object, _text: str) -> None:
        msg = "edit failed"
        raise RuntimeError(msg)

    with caplog.at_level(logging.WARNING, logger="bot.handlers.chat"):
        await deliver_final_response(
            message=message,
            response="abcdef",
            status=object(),
            safe_edit=broken_edit,
            options=DeliveryOptions(
                formatter=lambda text: text,
                splitter=_split,
                max_message_length=3,
                user_id=42,
            ),
        )

    assert message.answers == [
        ("abc", {"parse_mode": "HTML"}),
        ("def", {"parse_mode": "HTML"}),
    ]
    assert "Sending complete response again" in caplog.text


@pytest.mark.asyncio
async def test_delivery_does_nothing_for_empty_formatted_response() -> None:
    """Delivery does nothing for empty formatted response."""
    message = FakeMessage()

    await deliver_final_response(
        message=message,
        response="anything",
        status=None,
        safe_edit=lambda *_args: None,
        options=DeliveryOptions(
            formatter=lambda _text: "",
        ),
    )

    assert message.answers == []


@pytest.mark.asyncio
async def test_delivery_splits_response_longer_than_telegram_message_limit() -> None:
    """Delivery splits response longer than telegram message limit."""
    message = FakeMessage()
    response = "x" * 3901

    await deliver_final_response(
        message=message,
        response=response,
        status=None,
        safe_edit=lambda *_args: None,
        options=DeliveryOptions(
            formatter=lambda text: text,
            splitter=_split,
        ),
    )

    assert [len(text) for text, _kwargs in message.answers] == [3900, 1]
    assert "".join(text for text, _kwargs in message.answers) == response
