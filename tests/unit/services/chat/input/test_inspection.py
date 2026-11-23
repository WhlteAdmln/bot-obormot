# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input inspection."""

from __future__ import annotations

from types import SimpleNamespace

from bot_obormot.services.chat.input import inspection as inspection_module
from tests.support.message_input import make_message


def no_media(_message: object) -> tuple[object, ...]:
    """No media."""
    return None, None


def no_audio(_message: object) -> tuple[object, ...]:
    """No audio."""
    return None, None


def test_inspect_message_marks_plain_text_and_ignores_commands() -> None:
    """Inspect message marks plain text and ignores commands."""
    message = make_message(text="Привет")
    info = inspection_module.inspect_message(
        message,
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )

    assert info.has_text is True
    assert info.has_content is True
    assert info.has_media is False
    assert info.has_audio is False
    assert info.has_document is False

    command = make_message(text="/start")
    command_info = inspection_module.inspect_message(
        command,
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )
    assert command_info.has_text is False
    assert command_info.has_content is False


def test_inspect_message_routes_image_documents_to_media() -> None:
    """Inspect message routes image documents to media."""
    document = SimpleNamespace(
        file_id="document-image-id",
        file_name="picture.bin",
        mime_type="image/png",
    )
    info = inspection_module.inspect_message(
        make_message(document=document, text=None),
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )

    assert info.file_id == "document-image-id"
    assert info.media_type == "image"
    assert info.has_media is True
    assert info.has_document is False


def test_inspect_message_keeps_non_image_documents_as_documents() -> None:
    """Inspect message keeps non image documents as documents."""
    document = SimpleNamespace(
        file_id="document-id",
        file_name="report.pdf",
        mime_type="application/pdf",
    )
    info = inspection_module.inspect_message(
        make_message(document=document, text=None),
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )

    assert info.file_id is None
    assert info.has_media is False
    assert info.has_document is True
