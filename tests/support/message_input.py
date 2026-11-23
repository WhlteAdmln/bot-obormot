# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for message input tests."""

from __future__ import annotations

from types import SimpleNamespace


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
