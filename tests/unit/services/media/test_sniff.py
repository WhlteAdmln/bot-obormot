# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media sniff."""

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.media.sniff import sniff_media_type, verify_declared_type
from bot_obormot.services.media.texts import (
    MEDIA_TYPE_MISMATCH,
    UNSUPPORTED_OR_DAMAGED_MEDIA_FILE,
)


def _rejection(data: bytes, declared: str) -> str:
    try:
        verify_declared_type(data, declared)
    except MediaError as error:
        return str(error)
    return ""


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"GIF87a" + b"\x01\x00", "gif"),
        (b"GIF89a" + b"\xff\xfe", "gif"),
        (b"\x1f\x8b" + b"\x08\x00", "tgs"),
        (b"\x1a\x45\xdf\xa3" + b"\x9f\x42", "webm"),
        (b"\x00\x00\x00\x18ftypmp42" + b"\x00\x01", "mp4"),
        (b"\x00\x00\x00\x20ftypisom", "mp4"),
        (b"\xff\xd8\xff" + b"\xe0\x10", "image"),
        (b"\x89PNG\r\n\x1a\n" + b"IHDR", "image"),
        (b"RIFF\x10\x00\x00\x00WEBP" + b"VP8 ", "image"),
        (b"BM" + b"\x36\x00", "image"),
        (b"II*\x00" + b"\x08\x00", "image"),
        (b"MM\x00*" + b"\x00\x08", "image"),
    ],
    ids=[
        "gif87a",
        "gif89a",
        "tgs",
        "webm",
        "mp4",
        "mp4-header-only",
        "jpeg",
        "png",
        "webp",
        "bmp",
        "tiff-le",
        "tiff-be",
    ],
)
def test_sniff_media_type_recognizes_supported_signatures(
    data: bytes, expected: str
) -> None:
    assert sniff_media_type(data) == expected, "the signature maps to a wrong type"


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"G",
        b"GIF88a-almost",
        b"\x00\x00\x00\x08ftyp",
        b"RIFF\x10\x00\x00\x00WAVE",
        b"RIFF\x00\x00WEBP",
        b"#!/bin/sh\nrm -rf /\n",
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"%PDF-1.7\n",
        b"PK\x03\x04zip-archive",
        b"\x00GIF89a",
    ],
    ids=[
        "empty",
        "one-byte",
        "unknown-gif-version",
        "short-mp4",
        "riff-wave",
        "short-riff",
        "shell-script",
        "svg",
        "pdf",
        "zip",
        "shifted-gif",
    ],
)
def test_sniff_media_type_rejects_unknown_or_truncated_data(data: bytes) -> None:
    assert sniff_media_type(data) is None, "unknown data must not get a media type"


@pytest.mark.parametrize(
    ("data", "declared"),
    [
        (b"GIF89a" + b"\x02\x00", "gif"),
        (b"\x1f\x8b" + b"\x08\x08", "tgs"),
        (b"\x89PNG\r\n\x1a\n" + b"IDAT", "image"),
        (b"\x1a\x45\xdf\xa3" + b"\x01\x00", "webm"),
        (b"\x00\x00\x00\x18ftypmp42" + b"\x7f", "mp4"),
        (b"\x1a\x45\xdf\xa3" + b"\x42\x86", "video"),
        (b"\x1a\x45\xdf\xa3" + b"\x42\xf7", "mp4"),
        (b"\x00\x00\x00\x1cftypM4V " + b"\x00", "webm"),
    ],
    ids=[
        "gif",
        "tgs",
        "image",
        "webm",
        "mp4",
        "webm-as-video",
        "webm-as-mp4",
        "mp4-as-webm",
    ],
)
def test_verify_declared_type_accepts_matching_types_and_video_family(
    data: bytes, declared: str
) -> None:
    expected_empty = ""
    assert _rejection(data, declared) == expected_empty, "a matching type must pass"


@pytest.mark.parametrize(
    ("data", "declared"),
    [
        (b"GIF89a" + b"\x03\x00", "mp4"),
        (b"\x89PNG\r\n\x1a\n" + b"tEXt", "tgs"),
        (b"\x1f\x8b" + b"\x08\x00", "image"),
        (b"\x1a\x45\xdf\xa3" + b"\x00", "gif"),
        (b"\xff\xd8\xff" + b"\xdb", "video"),
        (b"GIF87a" + b"\x04", "GIF"),
        (b"\x89PNG\r\n\x1a\n", ""),
    ],
    ids=[
        "gif-as-mp4",
        "png-as-tgs",
        "gzip-as-image",
        "webm-as-gif",
        "jpeg-as-video",
        "upper-case-declared",
        "empty-declared",
    ],
)
def test_verify_declared_type_rejects_a_mismatched_type(
    data: bytes, declared: str
) -> None:
    assert _rejection(data, declared) == MEDIA_TYPE_MISMATCH, (
        "a type mismatch must be reported"
    )


@pytest.mark.parametrize(
    "data",
    [b"<html><script>alert(1)</script>", b"", b"\x7fELF\x02\x01\x01"],
    ids=["html", "empty", "elf"],
)
def test_verify_declared_type_rejects_an_unknown_signature(data: bytes) -> None:
    assert _rejection(data, "image") == UNSUPPORTED_OR_DAMAGED_MEDIA_FILE, (
        "an unknown signature must be refused as unsupported"
    )
