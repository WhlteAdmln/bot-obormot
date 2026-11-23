# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for streaming settings."""

from bot_obormot.services.chat.streaming.settings import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
)


def test_streaming_settings_preserve_original_values() -> None:
    """Streaming settings preserve original values."""
    assert STREAM_TOKEN_THRESHOLD == 150
    assert STREAM_UPDATE_INTERVAL == 0.8
    assert MAX_MESSAGE_LENGTH == 3900
