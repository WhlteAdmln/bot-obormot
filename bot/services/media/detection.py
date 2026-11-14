# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Detection of media attached to Telegram messages."""

from aiogram.types import Document, Message, Sticker


def _sticker_media_info(sticker: Sticker) -> tuple[str, str]:
    """Returns the file_id and media type of a sticker."""
    if sticker.is_animated:
        return sticker.file_id, "tgs"

    if sticker.is_video:
        return sticker.file_id, "webm"

    return sticker.file_id, "image"


def _document_media_info(document: Document) -> tuple[str, str] | None:
    """Returns the file_id and media type of a GIF or video document."""
    filename = (document.file_name or "").lower()
    mime_type = (document.mime_type or "").lower()

    if filename.endswith(".gif") or mime_type == "image/gif":
        return document.file_id, "gif"

    if filename.endswith(".webm") or mime_type == "video/webm":
        return document.file_id, "webm"

    if filename.endswith(".mp4") or mime_type == "video/mp4":
        return document.file_id, "mp4"

    return None


def get_media_info(message: Message) -> tuple[str | None, str | None]:
    """Определяет тип и file_id входящего медиа."""
    if message.photo:
        return message.photo[-1].file_id, "image"

    if message.animation:
        return message.animation.file_id, "mp4"

    if message.video:
        return message.video.file_id, "mp4"

    if message.sticker:
        return _sticker_media_info(message.sticker)

    if message.document:
        document_info = _document_media_info(message.document)

        if document_info is not None:
            return document_info

    return None, None
