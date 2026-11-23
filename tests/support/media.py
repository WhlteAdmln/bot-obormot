# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for media tests."""

from types import SimpleNamespace


def make_message(**values: object) -> SimpleNamespace:
    """Make message."""
    defaults = {
        "photo": None,
        "animation": None,
        "video": None,
        "sticker": None,
        "document": None,
        "caption": None,
        "text": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)
