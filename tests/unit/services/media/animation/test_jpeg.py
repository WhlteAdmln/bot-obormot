# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation jpeg."""

import io

from PIL import Image

from bot_obormot.services.media.animation.jpeg import image_to_bytes


def test_image_to_bytes_encodes_a_jpeg_frame() -> None:
    source = Image.new("RGBA", (1400, 900), (30, 60, 90, 128))
    encoded = image_to_bytes(source)
    expected_format = "JPEG"
    with Image.open(io.BytesIO(encoded)) as image:
        actual_format = image.format
    assert actual_format == expected_format, "the frame is not a JPEG"


def test_image_to_bytes_bounds_the_longest_side() -> None:
    source = Image.new("RGBA", (930, 1610), (200, 14, 66, 255))
    encoded = image_to_bytes(source)
    expected_max = 768
    with Image.open(io.BytesIO(encoded)) as image:
        longest_side = max(image.size)
    assert longest_side <= expected_max, "the frame is larger than the bound"


def test_image_to_bytes_drops_the_alpha_channel() -> None:
    source = Image.new("RGBA", (321, 47), (7, 180, 240, 9))
    encoded = image_to_bytes(source)
    expected_mode = "RGB"
    with Image.open(io.BytesIO(encoded)) as image:
        actual_mode = image.mode
    assert actual_mode == expected_mode, "the frame is not RGB"
