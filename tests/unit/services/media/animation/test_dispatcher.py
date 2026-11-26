# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation dispatcher."""

import asyncio
from collections.abc import Callable

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.media import animation
from bot_obormot.services.media.animation.dispatcher import dispatch_extraction


def recording_extractors(
    calls: list[tuple[str, bytes]],
) -> dict[str, Callable[[bytes], list[bytes]]]:
    """Make extractors that record their calls."""

    def gif(data: bytes) -> list[bytes]:
        calls.append(("gif", data))
        return [b"g"]

    def tgs_decoder(data: bytes) -> list[bytes]:
        calls.append(("tgs", data))
        return [b"t"]

    def video_decoder(data: bytes) -> list[bytes]:
        calls.append(("video", data))
        return [b"v"]

    return {
        "gif_extractor": gif,
        "tgs_extractor": tgs_decoder,
        "video_extractor": video_decoder,
    }


@pytest.mark.parametrize(
    ("data", "media_type", "expected"),
    [
        (b"1", "gif", [b"g"]),
        (b"2", "tgs", [b"t"]),
        (b"3", "mp4", [b"v"]),
    ],
)
def test_dispatch_extraction_returns_the_frames_of_the_matching_extractor(
    data: bytes, media_type: str, expected: list[bytes]
) -> None:
    calls: list[tuple[str, bytes]] = []
    extractors = recording_extractors(calls)
    result = dispatch_extraction(data, media_type, **extractors)
    assert result == expected, "the format was routed to a wrong extractor"


@pytest.mark.parametrize(
    ("data", "media_type", "expected"),
    [
        (b"GIF-17", "gif", [("gif", b"GIF-17")]),
        (b"lottie-4", "tgs", [("tgs", b"lottie-4")]),
        (b"mp4-box-9", "mp4", [("video", b"mp4-box-9")]),
    ],
)
def test_dispatch_extraction_calls_only_the_matching_extractor(
    data: bytes, media_type: str, expected: list[tuple[str, bytes]]
) -> None:
    calls: list[tuple[str, bytes]] = []
    extractors = recording_extractors(calls)
    dispatch_extraction(data, media_type, **extractors)
    assert calls == expected, "the extractor got a wrong call"


@pytest.mark.asyncio
async def test_animation_dispatch_errors_are_wrapped_as_media_error() -> None:
    data = b"data"
    expected = "Failed to process unknown animation"
    with pytest.raises(MediaError, match="unknown animation") as caught:
        await animation.extract_animation_frames(data, "unknown", asyncio.Semaphore(1))
    assert str(caught.value) == expected, "the dispatch error was not wrapped"
