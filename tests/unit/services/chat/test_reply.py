# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat reply."""

from types import SimpleNamespace

from bot_obormot.services.chat.reply import ReplyTarget
from tests.support.chat_streaming import (
    FakeReplyMessage,
)


def test_reply_target_stores_ids_and_builds_reply_parameters() -> None:
    """Store chat_id and message_id and allow sending without the reply."""
    target = ReplyTarget.from_message(FakeReplyMessage(message_id=42))
    parameters = target.parameters()

    assert (target.chat_id, target.message_id) == (5, 42)
    assert parameters is not None
    assert parameters.message_id == 42
    assert parameters.allow_sending_without_reply is True


def test_reply_target_without_message_id_has_no_parameters() -> None:
    """Do not build reply parameters when there is nothing to reply to."""
    assert ReplyTarget.from_message(SimpleNamespace()).parameters() is None
