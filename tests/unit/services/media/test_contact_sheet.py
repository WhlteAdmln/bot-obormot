# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media contact sheet."""

import io

import pytest
from PIL import Image

from bot_obormot.services.media.animation.limits import MAX_FRAMES
from bot_obormot.services.media.contact_sheet import build_contact_sheet


def jpeg_frames(
    colors: list[tuple[int, int, int]], size: tuple[int, int]
) -> list[bytes]:
    """Encode one solid JPEG frame per color."""
    frames = []
    for color in colors:
        output = io.BytesIO()
        Image.new("RGB", size, color).save(output, format="JPEG")
        frames.append(output.getvalue())
    return frames


def test_build_contact_sheet_combines_frames_into_a_jpeg() -> None:
    colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    frames = jpeg_frames(colors, (40, 30))
    result = build_contact_sheet(frames)
    expected_format = "JPEG"
    with Image.open(io.BytesIO(result)) as sheet:
        actual_format = sheet.format
    assert actual_format == expected_format, "the contact sheet is not a JPEG"


def test_build_contact_sheet_lays_four_frames_on_a_three_by_two_grid() -> None:
    colors = [(12, 200, 77), (90, 3, 140), (250, 128, 9), (31, 31, 220)]
    frames = jpeg_frames(colors, (52, 19))
    result = build_contact_sheet(frames)
    expected_size = (3 * 512, 2 * 384)
    with Image.open(io.BytesIO(result)) as sheet:
        actual_size = sheet.size
    assert actual_size == expected_size, "the contact sheet grid has a wrong size"


def test_build_contact_sheet_returns_single_frame_unchanged() -> None:
    frame = b"one-frame"
    assert build_contact_sheet([frame]) == frame, "a single frame was changed"


def test_build_contact_sheet_rejects_empty_frames() -> None:
    frames: list[bytes] = []
    expected = "Cannot build a contact sheet without frames"
    with pytest.raises(ValueError, match="without frames") as caught:
        build_contact_sheet(frames)
    assert str(caught.value) == expected, "an empty frame list was not rejected"


def test_build_contact_sheet_rejects_excessive_frames() -> None:
    frames = [b"surplus-frame"] * (MAX_FRAMES + 1)
    expected = f"Contact sheet supports at most {MAX_FRAMES} frames"
    with pytest.raises(ValueError, match="at most") as caught:
        build_contact_sheet(frames)
    assert str(caught.value) == expected, "too many frames were not rejected"
