# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat reply."""

from types import SimpleNamespace

from bot_obormot.services.chat.reply import ReplyTarget
from tests.support.chat_streaming import (
    FakeReplyMessage,
)


def test_reply_target_stores_the_chat_id() -> None:
    message_id = 42
    expected_chat_id = 5
    target = ReplyTarget.from_message(FakeReplyMessage(message_id=message_id))
    assert target.chat_id == expected_chat_id, "the chat id was not taken over"


def test_reply_target_stores_the_message_id() -> None:
    message_id = 731
    target = ReplyTarget.from_message(FakeReplyMessage(message_id=message_id))
    assert target.message_id == message_id, "the message id was not taken over"


def test_reply_target_builds_parameters_for_the_message_id() -> None:
    message_id = 1093
    parameters = ReplyTarget.from_message(
        FakeReplyMessage(message_id=message_id)
    ).parameters()
    actual_id = parameters.message_id if parameters is not None else None
    assert actual_id == message_id, "the reply parameters point to another message"


def test_reply_target_allows_sending_without_the_replied_message() -> None:
    message_id = 58
    parameters = ReplyTarget.from_message(
        FakeReplyMessage(message_id=message_id)
    ).parameters()
    allowed = parameters.allow_sending_without_reply if parameters else None
    assert allowed is True, "the reply must not require the original message"


def test_reply_target_without_message_id_has_no_parameters() -> None:
    parameters = ReplyTarget.from_message(SimpleNamespace()).parameters()
    assert parameters is None, "a message without an id produced reply parameters"
