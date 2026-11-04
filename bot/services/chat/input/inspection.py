"""Определение типов и наличия содержимого Telegram-сообщения."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from bot.services.chat.input.models import MessageInfo

if TYPE_CHECKING:
    from aiogram.types import Message


def inspect_message(
    message: Message,
    *,
    media_info_getter: Callable | None = None,
    audio_info_getter: Callable | None = None,
) -> MessageInfo:
    """Определяет типы содержимого входящего сообщения."""

    if media_info_getter is None:
        from bot.services.media import get_media_info

        media_info_getter = get_media_info

    if audio_info_getter is None:
        from bot.services.audio import get_audio_info

        audio_info_getter = get_audio_info

    file_id, media_type = media_info_getter(message)
    audio_file_id, audio_filename = audio_info_getter(message)

    document = message.document

    # Изображения, отправленные как документы,
    # направляем в существующий Vision Engine.
    if document and not file_id:
        filename = (document.file_name or "").lower()
        mime_type = (document.mime_type or "").lower()

        image_extensions = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".bmp",
            ".tif",
            ".tiff",
        )

        is_image_document = mime_type.startswith("image/") or filename.endswith(
            image_extensions
        )

        if is_image_document:
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
