# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation gif."""

import io
import struct
import warnings

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation.gif import extract_gif


def tiny_gif(width: int, height: int) -> bytes:
    """Минимальный GIF с указанным логическим размером холста."""
    header = b"GIF89a" + struct.pack("<HHBBB", width, height, 0x80, 0, 0)
    header += bytes([0, 0, 0, 255, 255, 255])
    frame = b"," + struct.pack("<HHHHB", 0, 0, 1, 1, 0) + bytes([2, 2, 0x44, 0x01, 0])
    return header + frame + b";"


def test_extract_gif_returns_at_most_six_jpeg_frames() -> None:
    """Extract gif returns at most six jpeg frames."""
    frames = [Image.new("RGB", (16, 12), (index * 20, 80, 160)) for index in range(9)]
    source = io.BytesIO()
    frames[0].save(
        source,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )

    extracted = extract_gif(source.getvalue())

    expected_count = 6
    assert len(extracted) == expected_count
    for frame in extracted:
        with Image.open(io.BytesIO(frame)) as image:
            expected_format = "JPEG"
            assert image.format == expected_format
            expected_mode = "RGB"
            assert image.mode == expected_mode


def test_huge_gif_canvas_is_rejected_before_frame_decode() -> None:
    """Huge gif canvas is rejected before frame decode."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with pytest.raises(MediaError, match="слишком большое"):
            extract_gif(tiny_gif(13000, 13000))


def test_gif_frame_count_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gif frame count limit is enforced."""
    frames = [Image.new("RGB", (2, 2), (index, 20, 30)) for index in range(3)]
    source = io.BytesIO()
    frames[0].save(
        source,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
    )
    monkeypatch.setattr("bot_obormot.services.media.animation.gif.MAX_GIF_FRAMES", 2)

    with pytest.raises(MediaError, match="слишком много кадров"):
        extract_gif(source.getvalue())
