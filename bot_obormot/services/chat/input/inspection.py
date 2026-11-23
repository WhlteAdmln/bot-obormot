# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Detect the content types and presence of Telegram message content."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot_obormot.services.audio import get_audio_info
from bot_obormot.services.chat.input.models import MessageInfo
from bot_obormot.services.media import get_media_info

if TYPE_CHECKING:
    from collections.abc import Callable

    from aiogram.types import Document, Message


_IMAGE_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
)


def _is_image_document(document: Document) -> bool:
    """Return whether the document's MIME type or file name says it is an image."""
    filename = (document.file_name or "").lower()
    mime_type = (document.mime_type or "").lower()
    return mime_type.startswith("image/") or filename.endswith(_IMAGE_EXTENSIONS)


def inspect_message(
    message: Message,
    *,
    media_info_getter: Callable[[Message], tuple[str | None, str | None]] | None = None,
    audio_info_getter: Callable[[Message], tuple[str | None, str | None]] | None = None,
) -> MessageInfo:
    """Detect the content types of an incoming message."""
    if media_info_getter is None:
        media_info_getter = get_media_info

    if audio_info_getter is None:
        audio_info_getter = get_audio_info

    file_id, media_type = media_info_getter(message)
    audio_file_id, audio_filename = audio_info_getter(message)

    document = message.document

    # Route images sent as documents
    # through the existing Vision Engine.
    if document and not file_id and _is_image_document(document):
        file_id = document.file_id
        media_type = "image"

    has_media = file_id is not None
    has_audio = audio_file_id is not None
    has_document = document is not None and not has_media
    has_text = bool(message.text and not message.text.startswith("/"))

    return MessageInfo(
        file_id=file_id,
        media_type=media_type,
        audio_file_id=audio_file_id,
        audio_filename=audio_filename,
        document=document,
        has_media=has_media,
        has_audio=has_audio,
        has_document=has_document,
        has_text=has_text,
    )
