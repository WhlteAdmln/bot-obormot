# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for streaming settings."""

from bot_obormot.services.chat.streaming.settings import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
)


def test_keeps_the_stream_token_threshold() -> None:
    expected_stream_token_threshold = 150
    assert expected_stream_token_threshold == STREAM_TOKEN_THRESHOLD, (
        "the stream token threshold changed"
    )


def test_keeps_the_stream_update_interval() -> None:
    expected_stream_update_interval = 0.8
    assert expected_stream_update_interval == STREAM_UPDATE_INTERVAL, (
        "the stream update interval changed"
    )


def test_keeps_the_max_message_length() -> None:
    expected_max_message_length = 3900
    assert expected_max_message_length == MAX_MESSAGE_LENGTH, (
        "the max message length changed"
    )
