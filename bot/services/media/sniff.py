# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Определение фактического типа медиа по сигнатуре содержимого."""

from bot.errors import MediaError

VIDEO_TYPES = {"webm", "mp4", "video"}
# Length of the ISO BMFF header (size + "ftyp" + brand) and of the RIFF header.
_MIN_HEADER_LENGTH = 12


def sniff_media_type(data: bytes) -> str | None:
    """Определяет поддерживаемый тип медиа по сигнатуре в начале файла."""
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"

    # TGS — gzip-сжатый JSON. Полную проверку потока выполняет validate_tgs.
    if data[:2] == b"\x1f\x8b":
        return "tgs"

    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm"

    # ISO Base Media File Format: ftyp box + four-byte major brand.
    if len(data) >= _MIN_HEADER_LENGTH and data[4:8] == b"ftyp":
        return "mp4"

    is_image = (
        data[:3] == b"\xff\xd8\xff"  # JPEG
        or data[:8] == b"\x89PNG\r\n\x1a\n"  # PNG
        or (
            len(data) >= _MIN_HEADER_LENGTH
            and data[:4] == b"RIFF"
            and data[8:12] == b"WEBP"
        )
        or data[:2] == b"BM"  # BMP
        or data[:4] in (b"II*\x00", b"MM\x00*")  # TIFF
    )

    return "image" if is_image else None


def verify_declared_type(data: bytes, declared: str) -> None:
    """Отклоняет файл, сигнатура которого не соответствует заявленному типу."""
    actual = sniff_media_type(data)

    if actual is None:
        msg = "Неподдерживаемый или повреждённый файл."
        raise MediaError(msg)

    same_video_family = declared in VIDEO_TYPES and actual in VIDEO_TYPES

    if actual != declared and not same_video_family:
        msg = "Тип файла не совпадает с его содержимым."
        raise MediaError(msg)
