# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for audio documents tests."""

import json
from collections.abc import AsyncIterator
from types import SimpleNamespace


class FakeContent:
    """Fake content."""

    def __init__(self, body: bytes) -> None:
        """Initializes the test double."""
        self._body = body

    async def iter_chunked(self, size: object) -> AsyncIterator[bytes]:
        """Iter chunked."""
        for start in range(0, len(self._body), size):
            yield self._body[start : start + size]


def json_body(payload: object) -> bytes:
    """Json body."""
    return json.dumps(payload).encode("utf-8")


def make_message(**values: object) -> SimpleNamespace:
    """Make message."""
    defaults = {"voice": None, "audio": None, "video_note": None}
    defaults.update(values)
    return SimpleNamespace(**defaults)
