# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for reply association and the formatting fallback."""

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError

from bot_obormot.services.chat.aggregation import aggregator as aggregator_module
from bot_obormot.services.chat.aggregation.aggregator import (
    AggregatedText,
    MessageAggregator,
)
from bot_obormot.services.chat.reply import ReplyTarget
from bot_obormot.services.chat.streaming.delivery import (
    DeliveryOptions,
    deliver_final_response,
)
from bot_obormot.services.chat.streaming.responder import StreamingResponder
from bot_obormot.services.chat.streaming.sending import is_entity_parse_error

PARSE_ERROR = "Bad Request: can't parse entities: Can't find end of the entity"


def _bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=SimpleNamespace(), message=text)  # type: ignore[arg-type]


def _network_error() -> TelegramNetworkError:
    return TelegramNetworkError(method=SimpleNamespace(), message="timeout")  # type: ignore[arg-type]


class _Message:
    def __init__(
        self,
        text: str = "x",
        message_id: int | None = 1,
        failures: list[Exception | None] | None = None,
    ) -> None:
        self.text = text
        self.message_id = message_id
        self.chat = SimpleNamespace(id=5)
        self.from_user = SimpleNamespace(id=9)
        self.answers: list[tuple[str, dict[str, object]]] = []
        self.failures = list(failures or [])

    async def answer(self, text: str, **kwargs: object) -> SimpleNamespace:
        self.answers.append((text, kwargs))
        if self.failures:
            failure = self.failures.pop(0)
            if failure is not None:
                raise failure
        return SimpleNamespace(text=text)


async def _edit(_status: object, _text: str, parse_mode: str | None = None) -> None:
    del parse_mode


def _options(message_id: int | None = 42) -> DeliveryOptions:
    return DeliveryOptions(reply_to=ReplyTarget(chat_id=5, message_id=message_id))


def test_reply_target_stores_ids_and_builds_reply_parameters() -> None:
    """Store chat_id and message_id and allow sending without the reply."""
    target = ReplyTarget.from_message(_Message(message_id=42))
    parameters = target.parameters()

    assert (target.chat_id, target.message_id) == (5, 42)
    assert parameters is not None
    assert parameters.message_id == 42
    assert parameters.allow_sending_without_reply is True


def test_reply_target_without_message_id_has_no_parameters() -> None:
    """Do not build reply parameters when there is nothing to reply to."""
    assert ReplyTarget.from_message(SimpleNamespace()).parameters() is None


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_bad_request(PARSE_ERROR), True),
        (_bad_request("Bad Request: chat not found"), False),
        (_network_error(), False),
        (RuntimeError("can't parse entities"), False),
    ],
)
def test_only_confirmed_parse_errors_are_entity_errors(
    error: Exception,
    expected: bool,
) -> None:
    """Recognize only Telegram formatting errors."""
    assert is_entity_parse_error(error) is expected


@pytest.mark.asyncio
async def test_parse_mode_and_reply_parameters_are_sent_together() -> None:
    """Send parse_mode and reply_parameters in one request."""
    message = _Message()

    await deliver_final_response(message, "**hi**", None, _edit, options=_options())

    ((text, kwargs),) = message.answers
    assert text == "*hi*"
    assert kwargs["parse_mode"] == "MarkdownV2"
    assert kwargs["reply_parameters"].message_id == 42


@pytest.mark.asyncio
async def test_plain_text_is_sent_without_parse_mode() -> None:
    """Do not pass parse_mode for plain text."""
    message = _Message()

    await deliver_final_response(message, "hello", None, _edit, options=_options())

    assert "parse_mode" not in message.answers[0][1]


@pytest.mark.asyncio
async def test_formatting_error_retries_once_with_original_text_and_reply() -> None:
    """Retry once without parse_mode, with the original text and the reply."""
    message = _Message(failures=[_bad_request(PARSE_ERROR), None])

    await deliver_final_response(message, "**hi** a.b", None, _edit, options=_options())

    assert len(message.answers) == 2
    retry_text, retry_kwargs = message.answers[1]
    assert retry_text == "**hi** a.b"
    assert "parse_mode" not in retry_kwargs
    assert retry_kwargs["reply_parameters"].message_id == 42


@pytest.mark.asyncio
async def test_failed_retry_is_logged_and_not_repeated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log the error when the retry fails too and do not retry again."""
    message = _Message(failures=[_bad_request(PARSE_ERROR), _bad_request(PARSE_ERROR)])

    with pytest.raises(TelegramBadRequest):
        await deliver_final_response(message, "**hi**", None, _edit, options=_options())

    assert len(message.answers) == 2
    assert "Plain-text retry failed" in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [_bad_request("Bad Request: chat not found"), _network_error()],
)
async def test_other_errors_do_not_trigger_the_fallback(error: Exception) -> None:
    """Never retry network errors or unrelated rejections."""
    message = _Message(failures=[error])

    with pytest.raises(type(error)):
        await deliver_final_response(message, "**hi**", None, _edit, options=_options())

    assert len(message.answers) == 1


@pytest.mark.asyncio
async def test_status_edit_falls_back_to_original_text() -> None:
    """Edit the streaming message again without parse_mode on a parse error."""
    edits: list[tuple[str, str | None]] = []

    async def edit(_status: object, text: str, parse_mode: str | None = None) -> None:
        edits.append((text, parse_mode))
        if parse_mode is not None:
            raise _bad_request(PARSE_ERROR)

    message = _Message()

    await deliver_final_response(
        message, "**hi**", SimpleNamespace(), edit, options=_options()
    )

    assert edits == [("*hi*", "MarkdownV2"), ("**hi**", None)]
    assert message.answers == []


@pytest.mark.asyncio
async def test_network_error_on_edit_does_not_send_a_duplicate() -> None:
    """Do not resend the response when the edit delivery status is unknown."""

    async def edit(_status: object, _text: str, parse_mode: str | None = None) -> None:
        del parse_mode
        raise _network_error()

    message = _Message()

    with pytest.raises(TelegramNetworkError):
        await deliver_final_response(
            message, "hi", SimpleNamespace(), edit, options=_options()
        )

    assert message.answers == []


@pytest.mark.asyncio
async def test_only_the_first_chunk_is_a_reply() -> None:
    """Link only the first part of a long response to the user's message."""
    message = _Message()

    await deliver_final_response(
        message, "слово " * 1500, None, _edit, options=_options()
    )

    assert len(message.answers) > 1
    assert "reply_parameters" in message.answers[0][1]
    assert all("reply_parameters" not in kwargs for _, kwargs in message.answers[1:])


@pytest.mark.asyncio
async def test_reply_association_does_not_depend_on_completion_order() -> None:
    """Each response keeps the reply target of its own request."""
    first, second = _Message(), _Message()

    async def finish(message: _Message, target: int, delay: float) -> None:
        await asyncio.sleep(delay)
        await deliver_final_response(
            message, "ответ", None, _edit, options=_options(target)
        )

    await asyncio.gather(finish(first, 10, 0.05), finish(second, 11, 0))

    assert first.answers[0][1]["reply_parameters"].message_id == 10
    assert second.answers[0][1]["reply_parameters"].message_id == 11


@pytest.mark.asyncio
async def test_streaming_message_is_created_as_a_reply_without_parse_mode() -> None:
    """Create the streaming message as a reply and show raw text."""
    message = _Message()

    async def count_tokens(_text: str) -> int:
        return 999

    responder = StreamingResponder(
        message,
        9,
        count_tokens,
        _edit,
        reply_to=ReplyTarget(chat_id=5, message_id=42),
    )

    await responder.on_update("a" * 400)

    ((_, kwargs),) = message.answers
    assert kwargs["reply_parameters"].message_id == 42
    assert "parse_mode" not in kwargs


@pytest.mark.asyncio
async def test_aggregated_text_remembers_the_last_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Link the combined request to the last message that was added."""
    monkeypatch.setattr(aggregator_module, "MESSAGE_AGGREGATION_WINDOW", 0.1)
    aggregator = MessageAggregator()
    first = _Message("p" * 4000, message_id=1)

    task = asyncio.create_task(aggregator.collect(first))
    await asyncio.sleep(0.01)
    assert await aggregator.collect(_Message("q", message_id=2)) is None
    assert await aggregator.collect(_Message("r", message_id=3)) is None

    result = await task

    assert isinstance(result, AggregatedText)
    assert result.endswith("q\nr")
    assert result.last_message is not None
    assert result.last_message.message_id == 3
