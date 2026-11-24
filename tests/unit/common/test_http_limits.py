# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for common http limits."""

from types import SimpleNamespace

import pytest

from bot_obormot.common.http_limits import read_limited_body
from tests.support.audio_documents import FakeContent


def _response(body: bytes, declared: int | None = None) -> SimpleNamespace:
    return SimpleNamespace(content_length=declared, content=FakeContent(body))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "declared", "limit"),
    [
        (b"short", 11, 10),
        (b"12345678901", None, 10),
        (b"lies-about-size", 3, 10),
        (b"x" * 70_000, None, 65_536),
        (b"\x00", None, 0),
    ],
    ids=[
        "declared-oversize",
        "streamed-oversize",
        "declared-small-streams-large",
        "oversize-across-chunks",
        "zero-limit",
    ],
)
async def test_returns_none_for_a_body_over_the_limit(
    body: bytes, declared: int | None, limit: int
) -> None:
    result = await read_limited_body(_response(body, declared), limit)
    assert result is None, "a body over the limit must be refused"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "declared", "limit"),
    [
        (b"1234567890", None, 10),
        (b"exact", 5, 5),
        (b"", 0, 0),
        (b"y" * 131_072, None, 131_072),
    ],
    ids=["at-limit-streamed", "at-limit-declared", "empty", "at-limit-many-chunks"],
)
async def test_returns_the_whole_body_within_the_limit(
    body: bytes, declared: int | None, limit: int
) -> None:
    result = await read_limited_body(_response(body, declared), limit)
    assert result == body, "a body within the limit must be returned whole"
