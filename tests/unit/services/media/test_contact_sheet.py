# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media contact sheet."""

import io

import pytest
from PIL import Image

from bot_obormot.services.media.animation.limits import MAX_FRAMES
from bot_obormot.services.media.contact_sheet import build_contact_sheet


def test_build_contact_sheet_combines_frames_into_one_jpeg() -> None:
    frames = []
    for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)):
        output = io.BytesIO()
        Image.new("RGB", (40, 30), color).save(output, format="JPEG")
        frames.append(output.getvalue())

    result = build_contact_sheet(frames)

    with Image.open(io.BytesIO(result)) as sheet:
        expected_format = "JPEG"
        assert sheet.format == expected_format
        assert sheet.size == (3 * 512, 2 * 384)


def test_build_contact_sheet_returns_single_frame_unchanged() -> None:
    frame = b"one-frame"
    assert build_contact_sheet([frame]) == frame


def test_build_contact_sheet_rejects_empty_or_excessive_frames() -> None:
    with pytest.raises(ValueError, match="without frames"):
        build_contact_sheet([])
    with pytest.raises(ValueError, match="at most"):
        build_contact_sheet([b"x"] * (MAX_FRAMES + 1))
