# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Detect the actual media type from the content signature."""

from bot_obormot.errors import MediaError
from bot_obormot.services.media.texts import (
    MEDIA_TYPE_MISMATCH,
    UNSUPPORTED_OR_DAMAGED_MEDIA_FILE,
)

GZIP_MAGIC = b"\x1f\x8b"
EBML_MAGIC = b"\x1a\x45\xdf\xa3"
FTYP_MARKER = b"ftyp"
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
RIFF_MAGIC = b"RIFF"
WEBP_MARKER = b"WEBP"
BMP_MAGIC = b"BM"
VIDEO_TYPES = {"webm", "mp4", "video"}
# Length of the ISO BMFF header (size + "ftyp" + brand) and of the RIFF header.
_MIN_HEADER_LENGTH = 12


def sniff_media_type(data: bytes) -> str | None:
    """Detect a supported media type from the file's leading signature."""
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "gif"

    # TGS is gzip-compressed JSON. validate_tgs performs full stream validation.
    if data[:2] == GZIP_MAGIC:
        return "tgs"

    if data[:4] == EBML_MAGIC:
        return "webm"

    # ISO Base Media File Format: ftyp box + four-byte major brand.
    if len(data) >= _MIN_HEADER_LENGTH and data[4:8] == FTYP_MARKER:
        return "mp4"

    is_image = (
        data[:3] == JPEG_MAGIC  # JPEG
        or data[:8] == PNG_MAGIC  # PNG
        or (
            len(data) >= _MIN_HEADER_LENGTH
            and data[:4] == RIFF_MAGIC
            and data[8:12] == WEBP_MARKER
        )
        or data[:2] == BMP_MAGIC  # BMP
        or data[:4] in {b"II*\x00", b"MM\x00*"}  # TIFF
    )

    return "image" if is_image else None


def verify_declared_type(data: bytes, declared: str) -> None:
    """Reject a file whose signature does not match its declared media type."""
    actual = sniff_media_type(data)

    if actual is None:
        msg = UNSUPPORTED_OR_DAMAGED_MEDIA_FILE
        raise MediaError(msg)

    same_video_family = declared in VIDEO_TYPES and actual in VIDEO_TYPES

    if actual != declared and not same_video_family:
        msg = MEDIA_TYPE_MISMATCH
        raise MediaError(msg)
