# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation jpeg."""

import io

from PIL import Image

from bot_obormot.services.media.animation.jpeg import image_to_bytes


def test_image_to_bytes_encodes_bounded_jpeg_frame() -> None:
    """Image to bytes encodes bounded jpeg frame."""
    source = Image.new("RGBA", (1400, 900), (30, 60, 90, 128))

    encoded = image_to_bytes(source)

    with Image.open(io.BytesIO(encoded)) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 768
        assert image.mode == "RGB"
