# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for common http limits."""

from types import SimpleNamespace

import pytest

from bot_obormot.common.http_limits import read_limited_body
from tests.support.audio_documents import FakeContent


@pytest.mark.asyncio
async def test_read_limited_body_rejects_declared_and_streamed_oversize() -> None:
    """Read limited body rejects declared and streamed oversize."""
    declared_oversize = SimpleNamespace(
        content_length=11,
        content=FakeContent(b"ignored"),
    )
    assert await read_limited_body(declared_oversize, 10) is None

    streamed_oversize = SimpleNamespace(
        content_length=None,
        content=FakeContent(b"12345678901"),
    )
    assert await read_limited_body(streamed_oversize, 10) is None

    within_limit = SimpleNamespace(
        content_length=None,
        content=FakeContent(b"1234567890"),
    )
    assert await read_limited_body(within_limit, 10) == b"1234567890"
