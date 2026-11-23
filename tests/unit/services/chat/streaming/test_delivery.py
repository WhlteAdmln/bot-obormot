# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for streaming delivery."""

import asyncio
import logging
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from bot_obormot.services.chat.formatting import FormattedChunk
from bot_obormot.services.chat.reply import ReplyTarget
from bot_obormot.services.chat.streaming.delivery import (
    DeliveryOptions,
    deliver_final_response,
)
from tests.support.chat_streaming import (
    PARSE_ERROR,
    FakeMessage,
    FakeReplyMessage,
    bad_request,
    edit_status,
    network_error,
    single_answer,
    split_text,
)


def _prepare(text: str, max_length: int) -> list[FormattedChunk]:
    return [
        FormattedChunk(text=chunk, parse_mode="HTML", plain_text=chunk)
        for chunk in split_text(text, max_length=max_length)
    ]


def _options(message_id: int | None = 42) -> DeliveryOptions:
    return DeliveryOptions(reply_to=ReplyTarget(chat_id=5, message_id=message_id))


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
            preparer=_prepare,
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

    async def safe_edit(
        status: object,
        text: str,
        **_kwargs: object,
    ) -> None:
        edits.append((status, text))

    status = object()
    await deliver_final_response(
        message=message,
        response="abcdefgh",
        status=status,
        safe_edit=safe_edit,
        options=DeliveryOptions(
            preparer=_prepare,
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

    async def broken_edit(
        _status: object,
        _text: str,
        **_kwargs: object,
    ) -> None:
        msg = "edit failed"
        raise RuntimeError(msg)

    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await deliver_final_response(
            message=message,
            response="abcdef",
            status=object(),
            safe_edit=broken_edit,
            options=DeliveryOptions(
                preparer=_prepare,
                max_message_length=3,
                user_id=42,
            ),
        )

    assert message.answers == [
        ("abc", {"parse_mode": "HTML"}),
        ("def", {"parse_mode": "HTML"}),
    ]
    expected_fragment = "Sending complete response again"
    assert expected_fragment in caplog.text


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
            preparer=lambda _text, _max_length: [],
        ),
    )

    expected_empty = []
    assert message.answers == expected_empty, "expected an empty list"


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
            preparer=_prepare,
        ),
    )

    assert [len(text) for text, _kwargs in message.answers] == [3900, 1]
    assert "".join(text for text, _kwargs in message.answers) == response


@pytest.mark.asyncio
async def test_parse_mode_and_reply_parameters_are_sent_together() -> None:
    """Send parse_mode and reply_parameters in one request."""
    message = FakeReplyMessage()

    await deliver_final_response(
        message, "**hi**", None, edit_status, options=_options()
    )

    text, kwargs = single_answer(message)
    expected_text = "*hi*"
    assert text == expected_text
    expected_parse_mode = "MarkdownV2"
    assert kwargs["parse_mode"] == expected_parse_mode
    expected_message_id = 42
    assert kwargs["reply_parameters"].message_id == expected_message_id


@pytest.mark.asyncio
async def test_plain_text_is_sent_without_parse_mode() -> None:
    """Do not pass parse_mode for plain text."""
    message = FakeReplyMessage()

    await deliver_final_response(
        message, "hello", None, edit_status, options=_options()
    )

    expected_fragment = "parse_mode"
    assert expected_fragment not in message.answers[0][1]


@pytest.mark.asyncio
async def test_formatting_error_retries_once_with_original_text_and_reply() -> None:
    """Retry once without parse_mode, with the original text and the reply."""
    message = FakeReplyMessage(failures=[bad_request(PARSE_ERROR), None])

    await deliver_final_response(
        message, "**hi** a.b", None, edit_status, options=_options()
    )

    expected_count = 2
    assert len(message.answers) == expected_count
    retry_text, retry_kwargs = message.answers[1]
    expected_retry_text = "**hi** a.b"
    assert retry_text == expected_retry_text
    expected_fragment = "parse_mode"
    assert expected_fragment not in retry_kwargs
    expected_message_id = 42
    assert retry_kwargs["reply_parameters"].message_id == expected_message_id


@pytest.mark.asyncio
async def test_failed_retry_is_logged_and_not_repeated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log the error when the retry fails too and do not retry again."""
    message = FakeReplyMessage(
        failures=[bad_request(PARSE_ERROR), bad_request(PARSE_ERROR)]
    )

    with pytest.raises(TelegramBadRequest):
        await deliver_final_response(
            message, "**hi**", None, edit_status, options=_options()
        )

    expected_count = 2
    assert len(message.answers) == expected_count
    expected_fragment = "Plain-text retry failed"
    assert expected_fragment in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [bad_request("Bad Request: chat not found"), network_error()],
)
async def test_other_errors_do_not_trigger_the_fallback(error: Exception) -> None:
    """Never retry network errors or unrelated rejections."""
    message = FakeReplyMessage(failures=[error])

    with pytest.raises(type(error)):
        await deliver_final_response(
            message, "**hi**", None, edit_status, options=_options()
        )

    assert len(message.answers) == 1


@pytest.mark.asyncio
async def test_status_edit_falls_back_to_original_text() -> None:
    """Edit the streaming message again without parse_mode on a parse error."""
    edits: list[tuple[str, str | None]] = []

    async def edit(_status: object, text: str, parse_mode: str | None = None) -> None:
        edits.append((text, parse_mode))
        if parse_mode is not None:
            raise bad_request(PARSE_ERROR)

    message = FakeReplyMessage()

    await deliver_final_response(
        message, "**hi**", SimpleNamespace(), edit, options=_options()
    )

    assert edits == [("*hi*", "MarkdownV2"), ("**hi**", None)]
    expected_empty = []
    assert message.answers == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_network_error_on_edit_does_not_send_a_duplicate() -> None:
    """Do not resend the response when the edit delivery status is unknown."""

    async def edit(_status: object, _text: str, parse_mode: str | None = None) -> None:
        del parse_mode
        raise network_error()

    message = FakeReplyMessage()

    with pytest.raises(TelegramNetworkError):
        await deliver_final_response(
            message, "hi", SimpleNamespace(), edit, options=_options()
        )

    expected_empty = []
    assert message.answers == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_only_the_first_chunk_is_a_reply() -> None:
    """Link only the first part of a long response to the user's message."""
    message = FakeReplyMessage()

    await deliver_final_response(
        message, "слово " * 1500, None, edit_status, options=_options()
    )

    assert len(message.answers) > 1
    expected_fragment = "reply_parameters"
    assert expected_fragment in message.answers[0][1]
    expected_fragment = "reply_parameters"
    assert all(expected_fragment not in kwargs for _, kwargs in message.answers[1:])


@pytest.mark.asyncio
async def test_reply_association_does_not_depend_on_completion_order() -> None:
    """Each response keeps the reply target of its own request."""
    first, second = FakeReplyMessage(), FakeReplyMessage()

    async def finish(message: FakeReplyMessage, target: int, delay: float) -> None:
        await asyncio.sleep(delay)
        await deliver_final_response(
            message, "ответ", None, edit_status, options=_options(target)
        )

    await asyncio.gather(finish(first, 10, 0.05), finish(second, 11, 0))

    expected_message_id = 10
    assert first.answers[0][1]["reply_parameters"].message_id == expected_message_id
    expected_message_id = 11
    assert second.answers[0][1]["reply_parameters"].message_id == expected_message_id
