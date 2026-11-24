# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media images."""

import base64
import io
import struct
import zlib

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media import images as media_images
from bot_obormot.services.media.texts import IMAGE_RESOLUTION_TOO_LARGE

DATA_URL_PREFIX = "data:image/jpeg;base64,"


def _encode(image: Image.Image, image_format: str = "PNG", **options: object) -> bytes:
    output = io.BytesIO()
    image.save(output, format=image_format, **options)
    return output.getvalue()


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))


def _png_header_only(width: int, height: int) -> bytes:
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", b"")
        + _png_chunk(b"IEND", b"")
    )


def _prepared(image_data: bytes) -> Image.Image:
    result = media_images.prepare_image(image_data)
    decoded = base64.b64decode(result.removeprefix(DATA_URL_PREFIX))
    with Image.open(io.BytesIO(decoded)) as image:
        image.load()
        return image


def _refusal(image_data: bytes) -> str:
    try:
        media_images.prepare_image(image_data)
    except MediaError as error:
        return str(error)
    return ""


def test_prepare_image_returns_a_jpeg_data_url() -> None:
    result = media_images.prepare_image(_encode(Image.new("RGB", (5, 3), "navy")))
    assert result.startswith(DATA_URL_PREFIX), "the result must be a JPEG data URL"


def test_prepare_image_encodes_the_image_as_rgb_jpeg() -> None:
    image = _prepared(_encode(Image.new("RGBA", (12, 8), (255, 0, 0, 0))))
    observed = (image.format, image.mode, image.size)
    expected = ("JPEG", "RGB", (12, 8))
    assert observed == expected, "the image must become an RGB JPEG of the same size"


@pytest.mark.parametrize(
    "size",
    [(7000, 6000), (40_000_001, 1), (6325, 6325)],
    ids=["area", "strip", "square"],
)
def test_prepare_image_rejects_a_declared_resolution_over_the_limit(
    size: tuple[int, int],
) -> None:
    assert _refusal(_png_header_only(*size)) == IMAGE_RESOLUTION_TOO_LARGE, (
        "an oversized header must be refused before decoding"
    )


def test_prepare_image_rejects_an_image_over_a_lowered_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(media_images, "MAX_IMAGE_PIXELS", 5)
    assert _refusal(_encode(Image.new("RGB", (3, 2)))) == IMAGE_RESOLUTION_TOO_LARGE, (
        "an image over the limit must be refused"
    )


def test_prepare_image_respects_pillow_decompression_bomb_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 5)
    image_data = _encode(Image.new("RGB", (3, 2)))
    with pytest.raises(Image.DecompressionBombWarning) as caught:
        media_images.prepare_image(image_data)
    bomb_note = "decompression bomb"
    assert bomb_note in str(caught.value), "Pillow must flag a bomb"


@pytest.mark.parametrize(
    "image_data",
    [b"not-an-image", b"", b"\x89PNG\r\n\x1a\n", b"<svg onload=alert(1)/>"],
    ids=["text", "empty", "png-magic-only", "svg"],
)
def test_prepare_image_rejects_a_corrupt_file(image_data: bytes) -> None:
    with pytest.raises(Image.UnidentifiedImageError) as caught:
        media_images.prepare_image(image_data)
    unidentified_note = "cannot identify image file"
    assert unidentified_note in str(caught.value), "unreadable data must not be decoded"


def test_prepare_image_applies_exif_rotation() -> None:
    exif = Image.Exif()
    exif[274] = 6
    image_data = _encode(Image.new("RGB", (4, 2), "red"), "JPEG", exif=exif)
    expected = (2, 4)
    assert _prepared(image_data).size == expected, "the EXIF rotation must be applied"


@pytest.mark.parametrize(
    ("mode", "color"),
    [("RGBA", (255, 0, 0, 0)), ("LA", (128, 0))],
    ids=["rgba", "la"],
)
def test_prepare_image_composites_alpha_channels_on_white(
    mode: str, color: tuple[int, ...]
) -> None:
    image = _prepared(_encode(Image.new(mode, (2, 2), color)))
    expected_min = 245
    assert min(image.getpixel((0, 0))) >= expected_min, "a transparent pixel is white"


def test_prepare_image_handles_palette_transparency() -> None:
    source = Image.new("P", (2, 2), 0)
    source.putpalette([255, 0, 0, 0, 0, 0] + [0] * 762)
    image = _prepared(_encode(source, transparency=0))
    expected_min = 245
    assert min(image.getpixel((0, 0))) >= expected_min, "a transparent pixel is white"


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((1600, 800), (1536, 768)),
        ((300, 4000), (115, 1536)),
        ((1536, 1536), (1536, 1536)),
    ],
    ids=["wide", "tall", "at-limit"],
)
def test_prepare_image_bounds_the_longest_side(
    size: tuple[int, int], expected: tuple[int, int]
) -> None:
    image = _prepared(_encode(Image.new("RGB", size, (20, 40, 60))))
    assert image.size == expected, "the longest side must be at most 1536 pixels"
