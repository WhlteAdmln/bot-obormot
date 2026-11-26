# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media detection."""

from types import SimpleNamespace

import pytest

from bot_obormot.services import media
from bot_obormot.services.media.detection import get_media_info
from tests.support.media import make_message


def test_get_media_info_prefers_photo_and_uses_largest_photo() -> None:
    message = make_message(
        photo=[SimpleNamespace(file_id="thumb-81"), SimpleNamespace(file_id="full-4k")],
    )
    expected = ("full-4k", "image")
    assert media.get_media_info(message) == expected, "the largest photo was not used"


def test_get_media_info_classifies_an_animated_sticker_as_tgs() -> None:
    message = make_message(
        sticker=SimpleNamespace(
            file_id="tgs-id",
            is_animated=True,
            is_video=False,
        ),
    )
    expected = ("tgs-id", "tgs")
    assert media.get_media_info(message) == expected, "an animated sticker is not tgs"


def test_get_media_info_classifies_a_video_sticker_as_webm() -> None:
    message = make_message(
        sticker=SimpleNamespace(
            file_id="webm-id",
            is_animated=False,
            is_video=True,
        ),
    )
    expected = ("webm-id", "webm")
    assert media.get_media_info(message) == expected, "a video sticker is not webm"


def test_get_media_info_classifies_a_gif_document_by_its_name() -> None:
    message = make_message(
        document=SimpleNamespace(
            file_id="gif-id",
            file_name="IMAGE.GIF",
            mime_type="application/octet-stream",
        ),
    )
    expected = ("gif-id", "gif")
    assert media.get_media_info(message) == expected, "a gif document is not gif"


def test_get_media_info_classifies_video_documents_by_mime_type() -> None:
    message = make_message(
        document=SimpleNamespace(
            file_id="video-id",
            file_name="clip.bin",
            mime_type="video/mp4",
        ),
    )
    expected = ("video-id", "mp4")
    assert media.get_media_info(message) == expected, "a video mime type is not mp4"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            make_message(photo=[SimpleNamespace(file_id="photo-id")]),
            ("photo-id", "image"),
        ),
        (
            make_message(
                animation=SimpleNamespace(file_id="animation-id"),
            ),
            ("animation-id", "mp4"),
        ),
        (
            make_message(video=SimpleNamespace(file_id="video-id")),
            ("video-id", "mp4"),
        ),
        (
            make_message(
                sticker=SimpleNamespace(
                    file_id="animated-id",
                    is_animated=True,
                    is_video=False,
                ),
            ),
            ("animated-id", "tgs"),
        ),
        (
            make_message(
                sticker=SimpleNamespace(
                    file_id="video-sticker-id",
                    is_animated=False,
                    is_video=True,
                ),
            ),
            ("video-sticker-id", "webm"),
        ),
        (
            make_message(
                sticker=SimpleNamespace(
                    file_id="static-sticker-id",
                    is_animated=False,
                    is_video=False,
                ),
            ),
            ("static-sticker-id", "image"),
        ),
        (
            make_message(
                document=SimpleNamespace(
                    file_id="gif-name",
                    file_name="IMAGE.GIF",
                    mime_type="application/octet-stream",
                ),
            ),
            ("gif-name", "gif"),
        ),
        (
            make_message(
                document=SimpleNamespace(
                    file_id="gif-mime",
                    file_name="image.bin",
                    mime_type="IMAGE/GIF",
                ),
            ),
            ("gif-mime", "gif"),
        ),
        (
            make_message(
                document=SimpleNamespace(
                    file_id="webm-name",
                    file_name="clip.WEBM",
                    mime_type=None,
                ),
            ),
            ("webm-name", "webm"),
        ),
        (
            make_message(
                document=SimpleNamespace(
                    file_id="webm-mime",
                    file_name="clip.bin",
                    mime_type="video/webm",
                ),
            ),
            ("webm-mime", "webm"),
        ),
        (
            make_message(
                document=SimpleNamespace(
                    file_id="mp4-name",
                    file_name="clip.MP4",
                    mime_type=None,
                ),
            ),
            ("mp4-name", "mp4"),
        ),
        (
            make_message(
                document=SimpleNamespace(
                    file_id="mp4-mime",
                    file_name="clip.bin",
                    mime_type="video/mp4",
                ),
            ),
            ("mp4-mime", "mp4"),
        ),
        (
            make_message(
                document=SimpleNamespace(
                    file_id="unknown-id",
                    file_name="report.pdf",
                    mime_type="application/pdf",
                ),
            ),
            (None, None),
        ),
        (make_message(), (None, None)),
    ],
)
def test_get_media_info_detects_message_media(
    message: SimpleNamespace,
    expected: tuple[str | None, str | None],
) -> None:
    assert get_media_info(message) == expected, "the media was misdetected"
