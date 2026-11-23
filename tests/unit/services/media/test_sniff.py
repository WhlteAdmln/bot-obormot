# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media sniff."""

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.media.sniff import sniff_media_type, verify_declared_type


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"GIF87a" + b"payload", "gif"),
        (b"GIF89a" + b"payload", "gif"),
        (b"\x1f\x8b" + b"payload", "tgs"),
        (b"\x1a\x45\xdf\xa3" + b"payload", "webm"),
        (b"\x00\x00\x00\x18ftypmp42" + b"payload", "mp4"),
        (b"\xff\xd8\xff" + b"payload", "image"),
        (b"\x89PNG\r\n\x1a\n" + b"payload", "image"),
        (b"RIFF\x00\x00\x00\x00WEBP" + b"payload", "image"),
        (b"BM" + b"payload", "image"),
        (b"II*\x00" + b"payload", "image"),
        (b"MM\x00*" + b"payload", "image"),
    ],
)
def test_sniff_media_type_recognizes_supported_signatures(
    data: object, expected: object
) -> None:
    """Sniff media type recognizes supported signatures."""
    assert sniff_media_type(data) == expected


def test_sniff_media_type_rejects_unknown_or_short_mp4_data() -> None:
    """Sniff media type rejects unknown or short mp4 data."""
    assert sniff_media_type(b"not-a-media-file") is None
    assert sniff_media_type(b"\x00\x00\x00\x08ftyp") is None


@pytest.mark.parametrize(
    ("data", "declared"),
    [
        (b"GIF89a" + b"payload", "gif"),
        (b"\x1f\x8b" + b"payload", "tgs"),
        (b"\x89PNG\r\n\x1a\n" + b"payload", "image"),
        (b"\x1a\x45\xdf\xa3" + b"payload", "webm"),
        (b"\x00\x00\x00\x18ftypmp42" + b"payload", "mp4"),
        (b"\x1a\x45\xdf\xa3" + b"payload", "video"),
        # Telegram may report either MP4 or WEBM for supported video inputs.
        (b"\x1a\x45\xdf\xa3" + b"payload", "mp4"),
        (b"\x00\x00\x00\x18ftypmp42" + b"payload", "webm"),
    ],
)
def test_verify_declared_type_accepts_matching_types_and_video_family(
    data: object, declared: object
) -> None:
    """Verify declared type accepts matching types and video family."""
    assert verify_declared_type(data, declared) is None


def test_verify_declared_type_rejects_mismatched_types() -> None:
    """Verify declared type rejects mismatched types."""
    with pytest.raises(MediaError, match="не совпадает"):
        verify_declared_type(b"GIF89a" + b"payload", "mp4")

    with pytest.raises(MediaError, match="не совпадает"):
        verify_declared_type(b"\x89PNG\r\n\x1a\n" + b"payload", "tgs")

    with pytest.raises(MediaError, match="Неподдерживаемый"):
        verify_declared_type(b"not-a-media-file", "image")
