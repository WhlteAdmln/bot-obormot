# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input models."""

from __future__ import annotations

from bot_obormot.services.chat.input import (
    MessageInfo,
)


def test_message_info_has_content_is_true_for_each_supported_kind() -> None:
    """Message info has content is true for each supported kind."""
    base = {
        "file_id": None,
        "media_type": None,
        "audio_file_id": None,
        "audio_filename": None,
        "document": None,
        "has_media": False,
        "has_audio": False,
        "has_document": False,
        "has_text": False,
    }
    assert MessageInfo(**base).has_content is False
    for field in ("has_media", "has_audio", "has_document", "has_text"):
        assert MessageInfo(**(base | {field: True})).has_content is True
