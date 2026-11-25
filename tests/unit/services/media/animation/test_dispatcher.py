# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation dispatcher."""

import asyncio

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.media import animation
from bot_obormot.services.media.animation.dispatcher import dispatch_extraction


def test_dispatch_extraction_routes_formats() -> None:
    calls: list[tuple[str, bytes]] = []

    def gif(data: bytes) -> list[bytes]:
        calls.append(("gif", data))
        return [b"g"]

    def tgs_decoder(data: bytes) -> list[bytes]:
        calls.append(("tgs", data))
        return [b"t"]

    def video_decoder(data: bytes) -> list[bytes]:
        calls.append(("video", data))
        return [b"v"]

    extractors = {
        "gif_extractor": gif,
        "tgs_extractor": tgs_decoder,
        "video_extractor": video_decoder,
    }

    assert dispatch_extraction(b"1", "gif", **extractors) == [b"g"]
    assert dispatch_extraction(b"2", "tgs", **extractors) == [b"t"]
    assert dispatch_extraction(b"3", "mp4", **extractors) == [b"v"]
    assert calls == [("gif", b"1"), ("tgs", b"2"), ("video", b"3")]


@pytest.mark.asyncio
async def test_animation_dispatch_errors_are_wrapped_as_media_error() -> None:
    with pytest.raises(MediaError, match="Failed to process unknown animation"):
        await animation.extract_animation_frames(
            b"data", "unknown", asyncio.Semaphore(1)
        )
