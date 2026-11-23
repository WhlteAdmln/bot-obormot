# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for message input tests."""

from __future__ import annotations

from types import SimpleNamespace

from bot_obormot.services.chat.input.models import MessageInfo


def make_message(**overrides: object) -> SimpleNamespace:
    """Make message."""
    values = {
        "text": "Привет",
        "caption": None,
        "document": None,
        "photo": None,
        "sticker": None,
        "voice": None,
        "audio": None,
        "video_note": None,
        "animation": None,
        "video": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_info(**fields: object) -> MessageInfo:
    """Describe a message with no content except the given fields."""
    values: dict[str, object] = {
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
    values.update(fields)
    return MessageInfo(**values)
