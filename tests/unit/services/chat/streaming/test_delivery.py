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


async def _deliver_with_status(
    response: str,
) -> tuple[object, list[tuple[object, str]], FakeMessage]:
    message = FakeMessage()
    edits: list[tuple[object, str]] = []

    async def safe_edit(status: object, text: str, **_kwargs: object) -> None:
        edits.append((status, text))

    status = object()
    await deliver_final_response(
        message=message,
        response=response,
        status=status,
        safe_edit=safe_edit,
        options=DeliveryOptions(preparer=_prepare, max_message_length=3, user_id=42),
    )
    return status, edits, message


async def _broken_edit(_status: object, _text: str, **_kwargs: object) -> None:
    msg = "edit failed"
    raise RuntimeError(msg)


async def _deliver_after_broken_edit(response: str) -> FakeMessage:
    message = FakeMessage()
    await deliver_final_response(
        message=message,
        response=response,
        status=object(),
        safe_edit=_broken_edit,
        options=DeliveryOptions(preparer=_prepare, max_message_length=3, user_id=42),
    )
    return message


async def _deliver_long(response: str) -> FakeMessage:
    message = FakeMessage()
    await deliver_final_response(
        message=message,
        response=response,
        status=None,
        safe_edit=lambda *_args: None,
        options=DeliveryOptions(preparer=_prepare),
    )
    return message


async def _deliver_reply(response: str, message: FakeReplyMessage) -> None:
    await deliver_final_response(
        message, response, None, edit_status, options=_options()
    )


async def _edit_with_markdown_failure(
    edits: list[tuple[str, str | None]], response: str
) -> FakeReplyMessage:
    async def edit(_status: object, text: str, parse_mode: str | None = None) -> None:
        edits.append((text, parse_mode))
        if parse_mode is not None:
            raise bad_request(PARSE_ERROR)

    message = FakeReplyMessage()
    await deliver_final_response(
        message, response, SimpleNamespace(), edit, options=_options()
    )
    return message


async def _deliver_in_reverse_order(
    first: FakeReplyMessage, second: FakeReplyMessage
) -> None:
    async def finish(message: FakeReplyMessage, target: int, delay: float) -> None:
        await asyncio.sleep(delay)
        await deliver_final_response(
            message, "ответ", None, edit_status, options=_options(target)
        )

    await asyncio.gather(finish(first, 10, 0.05), finish(second, 11, 0))


@pytest.mark.asyncio
async def test_delivery_sends_all_chunks_without_streaming_status() -> None:
    message = FakeMessage()
    response = "abcdefgh"
    expected_answers = [
        ("abc", {"parse_mode": "HTML"}),
        ("def", {"parse_mode": "HTML"}),
        ("gh", {"parse_mode": "HTML"}),
    ]

    await deliver_final_response(
        message=message,
        response=response,
        status=None,
        safe_edit=lambda *_args: None,
        options=DeliveryOptions(
            preparer=_prepare,
            max_message_length=3,
        ),
    )

    assert message.answers == expected_answers, "the chunks were not all sent"


@pytest.mark.asyncio
async def test_delivery_edits_the_status_with_the_first_chunk() -> None:
    response = "qwertyui"
    status, edits, _message = await _deliver_with_status(response)
    expected_edits = [(status, "qwe")]
    assert edits == expected_edits, "the status was not edited with the first chunk"


@pytest.mark.asyncio
async def test_delivery_sends_the_remaining_chunks_after_the_status_edit() -> None:
    response = "zxcvbnm1"
    expected_answers = [
        ("vbn", {"parse_mode": "HTML"}),
        ("m1", {"parse_mode": "HTML"}),
    ]
    _status, _edits, message = await _deliver_with_status(response)
    assert message.answers == expected_answers, "the remaining chunks were not sent"


@pytest.mark.asyncio
async def test_delivery_falls_back_to_all_chunks_when_status_edit_fails() -> None:
    response = "pqrstu"
    expected_answers = [
        ("pqr", {"parse_mode": "HTML"}),
        ("stu", {"parse_mode": "HTML"}),
    ]
    message = await _deliver_after_broken_edit(response)
    assert message.answers == expected_answers, "the fallback did not send all chunks"


@pytest.mark.asyncio
async def test_delivery_logs_a_warning_when_status_edit_fails(
    caplog: pytest.LogCaptureFixture,
) -> None:
    response = "lmn0p"
    retry_warning = "Sending complete response again"
    with caplog.at_level(logging.WARNING, logger="bot_obormot.handlers.chat"):
        await _deliver_after_broken_edit(response)
    assert retry_warning in caplog.text, "the resend warning was not logged"


@pytest.mark.asyncio
async def test_delivery_does_nothing_for_empty_formatted_response() -> None:
    message = FakeMessage()
    response = "anything"

    await deliver_final_response(
        message=message,
        response=response,
        status=None,
        safe_edit=lambda *_args: None,
        options=DeliveryOptions(
            preparer=lambda _text, _max_length: [],
        ),
    )

    expected_empty: list[tuple[str, dict[str, object]]] = []
    assert message.answers == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_delivery_splits_response_longer_than_telegram_message_limit() -> None:
    response = "x" * 3901
    expected_lengths = [3900, 1]
    message = await _deliver_long(response)
    lengths = [len(text) for text, _kwargs in message.answers]
    assert lengths == expected_lengths, "the response was not split at the limit"


@pytest.mark.asyncio
async def test_delivery_split_chunks_join_back_to_the_response() -> None:
    response = "юя7" * 1302
    message = await _deliver_long(response)
    joined = "".join(text for text, _kwargs in message.answers)
    assert joined == response, "the split chunks lost or changed text"


@pytest.mark.asyncio
async def test_sends_markdown_converted_to_markdown_v2_text() -> None:
    message = FakeReplyMessage()
    response = "**hi**"
    expected_text = "*hi*"
    await _deliver_reply(response, message)
    text, _kwargs = single_answer(message)
    assert text == expected_text, "the markdown was not converted"


@pytest.mark.asyncio
async def test_sends_markdown_v2_parse_mode_for_formatted_text() -> None:
    message = FakeReplyMessage()
    response = "**ok go**"
    expected_parse_mode = "MarkdownV2"
    await _deliver_reply(response, message)
    _text, kwargs = single_answer(message)
    assert kwargs["parse_mode"] == expected_parse_mode, "the parse mode is missing"


@pytest.mark.asyncio
async def test_sends_reply_parameters_together_with_parse_mode() -> None:
    message = FakeReplyMessage()
    response = "**ответ**"
    expected_message_id = 42
    await _deliver_reply(response, message)
    _text, kwargs = single_answer(message)
    reply = kwargs["reply_parameters"]
    assert reply.message_id == expected_message_id, "the reply target is wrong"


@pytest.mark.asyncio
async def test_plain_text_is_sent_without_parse_mode() -> None:
    message = FakeReplyMessage()
    response = "Обычный ответ без разметки"
    parse_mode_field = "parse_mode"
    await _deliver_reply(response, message)
    assert parse_mode_field not in message.answers[0][1], "plain text got a parse mode"


@pytest.mark.asyncio
async def test_formatting_error_retries_exactly_once() -> None:
    message = FakeReplyMessage(failures=[bad_request(PARSE_ERROR), None])
    response = "**hi** a.b"
    expected_count = 2
    await _deliver_reply(response, message)
    assert len(message.answers) == expected_count, "the retry count is wrong"


@pytest.mark.asyncio
async def test_formatting_error_retries_with_the_original_text() -> None:
    message = FakeReplyMessage(failures=[bad_request(PARSE_ERROR), None])
    response = "**жирный** b.c"
    await _deliver_reply(response, message)
    retry_text, _retry_kwargs = message.answers[1]
    assert retry_text == response, "the retry did not use the original text"


@pytest.mark.asyncio
async def test_formatting_error_retries_without_parse_mode() -> None:
    message = FakeReplyMessage(failures=[bad_request(PARSE_ERROR), None])
    response = "**go** 1.5"
    parse_mode_field = "parse_mode"
    await _deliver_reply(response, message)
    _retry_text, retry_kwargs = message.answers[1]
    assert parse_mode_field not in retry_kwargs, "the retry kept the parse mode"


@pytest.mark.asyncio
async def test_formatting_error_retry_keeps_the_reply_target() -> None:
    message = FakeReplyMessage(failures=[bad_request(PARSE_ERROR), None])
    response = "**q** z.y"
    expected_message_id = 42
    await _deliver_reply(response, message)
    _retry_text, retry_kwargs = message.answers[1]
    reply = retry_kwargs["reply_parameters"]
    assert reply.message_id == expected_message_id, "the retry lost the reply target"


@pytest.mark.asyncio
async def test_failed_retry_is_not_repeated() -> None:
    message = FakeReplyMessage(
        failures=[bad_request(PARSE_ERROR), bad_request(PARSE_ERROR)]
    )
    response = "**hi**"
    expected_count = 2
    with pytest.raises(TelegramBadRequest):
        await _deliver_reply(response, message)
    assert len(message.answers) == expected_count, "the retry was repeated"


@pytest.mark.asyncio
async def test_failed_retry_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    message = FakeReplyMessage(
        failures=[bad_request(PARSE_ERROR), bad_request(PARSE_ERROR)]
    )
    response = "**снова**"
    retry_warning = "Plain-text retry failed"
    with pytest.raises(TelegramBadRequest):
        await _deliver_reply(response, message)
    assert retry_warning in caplog.text, "the failed retry was not logged"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [bad_request("Bad Request: chat not found"), network_error()],
)
async def test_other_errors_do_not_trigger_the_fallback(error: Exception) -> None:
    message = FakeReplyMessage(failures=[error])
    response = "**hi**"
    expected_count = 1

    with pytest.raises(type(error)):
        await _deliver_reply(response, message)

    assert len(message.answers) == expected_count, "the fallback was triggered"


@pytest.mark.asyncio
async def test_status_edit_falls_back_to_original_text() -> None:
    edits: list[tuple[str, str | None]] = []
    response = "**hi**"
    expected_edits = [("*hi*", "MarkdownV2"), ("**hi**", None)]
    await _edit_with_markdown_failure(edits, response)
    assert edits == expected_edits, "the edit did not fall back to the original text"


@pytest.mark.asyncio
async def test_status_edit_fallback_sends_no_new_message() -> None:
    edits: list[tuple[str, str | None]] = []
    response = "**статус**"
    message = await _edit_with_markdown_failure(edits, response)
    expected_empty: list[tuple[str, dict[str, object]]] = []
    assert message.answers == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_network_error_on_edit_does_not_send_a_duplicate() -> None:

    async def edit(_status: object, _text: str, parse_mode: str | None = None) -> None:
        del parse_mode
        raise network_error()

    message = FakeReplyMessage()
    response = "hi"

    with pytest.raises(TelegramNetworkError):
        await deliver_final_response(
            message, response, SimpleNamespace(), edit, options=_options()
        )

    expected_empty: list[tuple[str, dict[str, object]]] = []
    assert message.answers == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_long_reply_is_sent_in_several_chunks() -> None:
    message = FakeReplyMessage()
    response = "слово " * 1500
    expected_minimum = 1
    await _deliver_reply(response, message)
    assert len(message.answers) > expected_minimum, "the reply was not split"


@pytest.mark.asyncio
async def test_first_chunk_of_a_long_reply_is_a_reply() -> None:
    message = FakeReplyMessage()
    response = "буква " * 1600
    reply_field = "reply_parameters"
    await _deliver_reply(response, message)
    assert reply_field in message.answers[0][1], "the first chunk is not a reply"


@pytest.mark.asyncio
async def test_later_chunks_of_a_long_reply_are_not_replies() -> None:
    message = FakeReplyMessage()
    response = "строка " * 1450
    reply_field = "reply_parameters"
    await _deliver_reply(response, message)
    later_replies = [reply_field in kwargs for _, kwargs in message.answers[1:]]
    assert not any(later_replies), "a later chunk is a reply"


@pytest.mark.asyncio
async def test_slow_reply_keeps_its_own_target() -> None:
    first, second = FakeReplyMessage(), FakeReplyMessage()
    expected_message_id = 10
    await _deliver_in_reverse_order(first, second)
    reply = first.answers[0][1]["reply_parameters"]
    assert reply.message_id == expected_message_id, "the slow reply lost its target"


@pytest.mark.asyncio
async def test_fast_reply_keeps_its_own_target() -> None:
    first, second = FakeReplyMessage(), FakeReplyMessage()
    expected_message_id = 11
    await _deliver_in_reverse_order(first, second)
    reply = second.answers[0][1]["reply_parameters"]
    assert reply.message_id == expected_message_id, "the fast reply lost its target"
