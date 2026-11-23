# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build the text representation of a message for chat history."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from bot_obormot.services.chat.input import texts

if TYPE_CHECKING:
    from aiogram.types import Document, Message

    from bot_obormot.services.chat.input.models import MessageInfo


def _audio_history_text(message: Message, transcribed_text: str | None) -> str:
    """Describe a voice message by its transcript and caption."""
    text = texts.AUDIO_HISTORY_TEMPLATE.format(transcribed_text=transcribed_text)

    if message.caption:
        text = f"{message.caption}\n\n{text}"

    return text


def _media_history_text(message: Message, info: MessageInfo) -> str:
    """Describe an image or animation, followed by the caption."""
    if info.media_type in {"tgs", "webm", "gif", "mp4"}:
        text = texts.ANIMATION_HISTORY_TEMPLATE.format(media_type=info.media_type)
    elif message.photo:
        text = texts.PHOTO_HISTORY_TEXT
    elif message.sticker:
        text = texts.STICKER_HISTORY_TEXT
    else:
        text = texts.IMAGE_HISTORY_TEXT

    if message.caption:
        text += f" {message.caption}"

    return text


def _document_history_text(
    message: Message,
    info: MessageInfo,
    document_format: str | None,
) -> str:
    """Describe a document by its name and format, followed by the caption."""
    # has_document is only set when the message carries a document.
    document = cast("Document", info.document)

    text = texts.DOCUMENT_HISTORY_TEMPLATE.format(
        filename=document.file_name or "document",
        document_format=cast("str", document_format).upper(),
    )

    if message.caption:
        text += f" {message.caption}"

    return text


def build_saved_user_text(
    message: Message,
    info: MessageInfo,
    *,
    text_override: str | None,
    transcribed_text: str | None,
    document_format: str | None,
) -> str | None:
    """Build the existing text description of a message for the database."""
    if info.has_audio:
        return _audio_history_text(message, transcribed_text)

    if info.has_media:
        return _media_history_text(message, info)

    if info.has_document:
        return _document_history_text(message, info, document_format)

    return text_override if text_override is not None else message.text
