# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation gif."""

import io
import struct
import warnings

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import gif
from bot_obormot.services.media.texts import GIF_TOO_MANY_FRAMES, IMAGE_TOO_LARGE


def _tiny_gif(width: int, height: int) -> bytes:
    header = b"GIF89a" + struct.pack("<HHBBB", width, height, 0x80, 0, 0)
    header += bytes([0, 0, 0, 255, 255, 255])
    frame = b"," + struct.pack("<HHHHB", 0, 0, 1, 1, 0) + bytes([2, 2, 0x44, 0x01, 0])
    return header + frame + b";"


def _animated_gif(count: int, size: tuple[int, int] = (16, 12)) -> bytes:
    frames = [Image.new("RGB", size, (index * 20, 80, 160)) for index in range(count)]
    source = io.BytesIO()
    frames[0].save(
        source, format="GIF", save_all=True, append_images=frames[1:], duration=70
    )
    return source.getvalue()


def _refusal(data: bytes) -> str:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        try:
            gif.extract_gif(data)
        except MediaError as error:
            return str(error)
    return ""


@pytest.mark.parametrize(
    ("count", "expected"),
    [(9, 6), (1, 1), (3, 3)],
    ids=["many", "single", "few"],
)
def test_extract_gif_returns_at_most_six_frames(count: int, expected: int) -> None:
    frames = gif.extract_gif(_animated_gif(count))
    assert len(frames) == expected, "the frame count must be capped at six"


def test_extract_gif_returns_rgb_jpeg_frames() -> None:
    observed = set()
    for frame in gif.extract_gif(_animated_gif(4)):
        with Image.open(io.BytesIO(frame)) as image:
            observed.add((image.format, image.mode))
    expected = {("JPEG", "RGB")}
    assert observed == expected, "every frame must be an RGB JPEG"


@pytest.mark.parametrize(
    "size",
    [(13000, 13000), (65535, 245), (65535, 65535)],
    ids=["square", "strip", "maximum"],
)
def test_huge_gif_canvas_is_rejected_before_frame_decode(
    size: tuple[int, int],
) -> None:
    assert _refusal(_tiny_gif(*size)) == IMAGE_TOO_LARGE, (
        "a huge canvas must be refused"
    )


def test_gif_frame_count_limit_is_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gif, "MAX_GIF_FRAMES", 2)
    assert _refusal(_animated_gif(3, (2, 2))) == GIF_TOO_MANY_FRAMES, (
        "too many frames must be refused"
    )


def test_gif_at_the_frame_count_limit_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gif, "MAX_GIF_FRAMES", 3)
    expected_empty = ""
    assert _refusal(_animated_gif(3, (2, 2))) == expected_empty, (
        "a GIF at the limit must pass"
    )
