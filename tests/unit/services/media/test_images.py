# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media images."""

import base64
import io

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services import media
from bot_obormot.services.media import images as media_images


def encode_image(image: Image.Image, image_format: str = "PNG") -> bytes:
    """Encode a Pillow image into an in-memory file."""
    output = io.BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_prepare_image_returns_jpeg_data_url_and_composites_transparency() -> None:
    source = Image.new("RGBA", (12, 8), (255, 0, 0, 0))
    output = io.BytesIO()
    source.save(output, format="PNG")

    result = media.prepare_image(output.getvalue())

    assert result.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        expected_format = "JPEG"
        assert image.format == expected_format
        expected_mode = "RGB"
        assert image.mode == expected_mode
        assert image.size == (12, 8)


def test_prepare_image_rejects_oversized_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(media_images, "MAX_IMAGE_PIXELS", 5)
    image_data = encode_image(Image.new("RGB", (3, 2)))

    with pytest.raises(MediaError, match="слишком большое"):
        media_images.prepare_image(image_data)


def test_prepare_image_respects_pillow_decompression_bomb_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 5)
    image_data = encode_image(Image.new("RGB", (3, 2)))

    with pytest.raises(Image.DecompressionBombWarning):
        media_images.prepare_image(image_data)


def test_prepare_image_rejects_corrupt_file() -> None:
    with pytest.raises(Image.UnidentifiedImageError):
        media_images.prepare_image(b"not-an-image")


def test_prepare_image_applies_exif_rotation() -> None:
    source = Image.new("RGB", (4, 2), "red")
    exif = Image.Exif()
    exif[274] = 6
    output = io.BytesIO()
    source.save(output, format="JPEG", exif=exif)

    result = media_images.prepare_image(output.getvalue())
    encoded = result.split(",", 1)[1]
    decoded = base64.b64decode(encoded)
    with Image.open(io.BytesIO(decoded)) as image:
        expected_format = "JPEG"
        assert image.format == expected_format
        assert image.size == (2, 4)


@pytest.mark.parametrize(
    ("mode", "color"),
    [
        ("RGBA", (255, 0, 0, 0)),
        ("LA", (128, 0)),
    ],
)
def test_prepare_image_composites_alpha_channels(
    mode: str,
    color: tuple[int, ...],
) -> None:
    image_data = encode_image(Image.new(mode, (2, 2), color))
    result = media_images.prepare_image(image_data)
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        expected_mode = "RGB"
        assert image.mode == expected_mode
        expected_min = 245
        assert min(image.getpixel((0, 0))) >= expected_min


def test_prepare_image_handles_palette_transparency() -> None:
    source = Image.new("P", (2, 2), 0)
    source.putpalette([255, 0, 0, 0, 0, 0] + [0] * 762)
    output = io.BytesIO()
    source.save(output, format="PNG", transparency=0)

    result = media_images.prepare_image(output.getvalue())
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        expected_mode = "RGB"
        assert image.mode == expected_mode
        expected_min = 245
        assert min(image.getpixel((0, 0))) >= expected_min


def test_prepare_image_converts_rgb_and_resizes_large_dimensions() -> None:
    image_data = encode_image(Image.new("RGB", (1600, 800), (20, 40, 60)))

    result = media_images.prepare_image(image_data)
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        expected_format = "JPEG"
        assert image.format == expected_format
        expected_mode = "RGB"
        assert image.mode == expected_mode
        assert image.size == (1536, 768)
