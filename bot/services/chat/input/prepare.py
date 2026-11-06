"""Координация подготовки текста, медиа, аудио и документов."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from bot.services.chat.input.audio_part import prepare_audio
from bot.services.chat.input.document_part import prepare_document
from bot.services.chat.input.media_part import prepare_media
from bot.services.chat.input.models import MessageInfo, PreparedMessage
from bot.services.chat.input.saved_text import build_saved_user_text
from bot.services.chat.input.user_content import build_user_content

if TYPE_CHECKING:
    from aiogram.types import Message

logger = logging.getLogger("bot.services.chat.input.prepare")


async def prepare_message(
    message: Message,
    info: MessageInfo,
    text_override: str | None = None,
) -> PreparedMessage:
    """Скачивает и обрабатывает входящие данные."""

    image_urls = None
    image_bytes = None
    transcribed_text = None
    document_text = None
    document_format = None

    # Порядок обработки намеренно сохранён: аудио, медиа, документ.
    if info.has_audio:
        transcribed_text = await prepare_audio(message, info)

    if info.has_media:
        image_urls, image_bytes = await prepare_media(message, info)

    if info.has_document:
        document_text, document_format = await prepare_document(message, info)

    user_content = build_user_content(
        message,
        info,
        text_override=text_override,
        transcribed_text=transcribed_text,
        image_urls=image_urls,
        document_text=document_text,
        document_format=document_format,
    )

    saved_user_text = build_saved_user_text(
        message,
        info,
        text_override=text_override,
        transcribed_text=transcribed_text,
        document_format=document_format,
    )

    return PreparedMessage(
        user_content=user_content,
        saved_user_text=saved_user_text,
        image_bytes=image_bytes,
    )
