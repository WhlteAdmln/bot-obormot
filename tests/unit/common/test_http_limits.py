# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for common http limits."""

from types import SimpleNamespace

import pytest

from bot_obormot.common.http_limits import read_body_prefix, read_limited_body
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "limit", "expected"),
    [
        (b"Kaffee-Fehler 503", 6, (b"Kaffee", True)),
        (b"z" * 70_001, 65_537, (b"z" * 65_537, True)),
        (b"\xff\x00\x7f", 0, (b"", True)),
        (b"ein Zeichen", 11, (b"ein Zeichen", False)),
        (b"", 4, (b"", False)),
    ],
    ids=["cut-in-first-chunk", "cut-in-later-chunk", "zero-limit", "at-limit", "empty"],
)
async def test_read_body_prefix_keeps_the_first_bytes_and_flags_the_rest(
    body: bytes, limit: int, expected: tuple[bytes, bool]
) -> None:
    result = await read_body_prefix(_response(body), limit)
    assert result == expected, "the prefix or the truncation flag is wrong"
