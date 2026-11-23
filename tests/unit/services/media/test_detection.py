# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media detection."""

from types import SimpleNamespace

import pytest

from bot_obormot.services import media
from bot_obormot.services.media.detection import get_media_info
from tests.support.media import make_message


def make_media_message(**overrides: object) -> SimpleNamespace:
    """Create a message with empty media fields."""
    values: dict[str, object] = {
        "photo": None,
        "animation": None,
        "video": None,
        "sticker": None,
        "document": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_media_info_prefers_photo_and_uses_largest_photo() -> None:
    """Get media info prefers photo and uses largest photo."""
    message = make_message(
        photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id="large")],
    )

    assert media.get_media_info(message) == ("large", "image")


def test_get_media_info_classifies_stickers_and_documents() -> None:
    """Get media info classifies stickers and documents."""
    animated_sticker = make_message(
        sticker=SimpleNamespace(
            file_id="tgs-id",
            is_animated=True,
            is_video=False,
        ),
    )
    video_sticker = make_message(
        sticker=SimpleNamespace(
            file_id="webm-id",
            is_animated=False,
            is_video=True,
        ),
    )
    gif_document = make_message(
        document=SimpleNamespace(
            file_id="gif-id",
            file_name="IMAGE.GIF",
            mime_type="application/octet-stream",
        ),
    )

    assert media.get_media_info(animated_sticker) == ("tgs-id", "tgs")
    assert media.get_media_info(video_sticker) == ("webm-id", "webm")
    assert media.get_media_info(gif_document) == ("gif-id", "gif")


def test_get_media_info_classifies_video_documents_by_mime_type() -> None:
    """Get media info classifies video documents by mime type."""
    message = make_message(
        document=SimpleNamespace(
            file_id="video-id",
            file_name="clip.bin",
            mime_type="video/mp4",
        ),
    )

    assert media.get_media_info(message) == ("video-id", "mp4")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            make_media_message(photo=[SimpleNamespace(file_id="photo-id")]),
            ("photo-id", "image"),
        ),
        (
            make_media_message(
                animation=SimpleNamespace(file_id="animation-id"),
            ),
            ("animation-id", "mp4"),
        ),
        (
            make_media_message(video=SimpleNamespace(file_id="video-id")),
            ("video-id", "mp4"),
        ),
        (
            make_media_message(
                sticker=SimpleNamespace(
                    file_id="animated-id",
                    is_animated=True,
                    is_video=False,
                ),
            ),
            ("animated-id", "tgs"),
        ),
        (
            make_media_message(
                sticker=SimpleNamespace(
                    file_id="video-sticker-id",
                    is_animated=False,
                    is_video=True,
                ),
            ),
            ("video-sticker-id", "webm"),
        ),
        (
            make_media_message(
                sticker=SimpleNamespace(
                    file_id="static-sticker-id",
                    is_animated=False,
                    is_video=False,
                ),
            ),
            ("static-sticker-id", "image"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="gif-name",
                    file_name="IMAGE.GIF",
                    mime_type="application/octet-stream",
                ),
            ),
            ("gif-name", "gif"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="gif-mime",
                    file_name="image.bin",
                    mime_type="IMAGE/GIF",
                ),
            ),
            ("gif-mime", "gif"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="webm-name",
                    file_name="clip.WEBM",
                    mime_type=None,
                ),
            ),
            ("webm-name", "webm"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="webm-mime",
                    file_name="clip.bin",
                    mime_type="video/webm",
                ),
            ),
            ("webm-mime", "webm"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="mp4-name",
                    file_name="clip.MP4",
                    mime_type=None,
                ),
            ),
            ("mp4-name", "mp4"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="mp4-mime",
                    file_name="clip.bin",
                    mime_type="video/mp4",
                ),
            ),
            ("mp4-mime", "mp4"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="unknown-id",
                    file_name="report.pdf",
                    mime_type="application/pdf",
                ),
            ),
            (None, None),
        ),
        (make_media_message(), (None, None)),
    ],
)
def test_get_media_info_detects_message_media(
    message: SimpleNamespace,
    expected: tuple[str | None, str | None],
) -> None:
    """Detect media types from message fields and document metadata."""
    assert get_media_info(message) == expected
