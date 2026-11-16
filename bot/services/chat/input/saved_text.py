# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build the text representation of a message for chat history."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from bot.services.chat.input import texts

if TYPE_CHECKING:
    from aiogram.types import Document, Message

    from bot.services.chat.input.models import MessageInfo


def build_saved_user_text(
    message: Message,
    info: MessageInfo,
    *,
    text_override: str | None,
    transcribed_text: str | None,
    document_format: str | None,
) -> str | None:
    """Build the existing text description of a message for the database."""
    saved_user_text: str | None

    if info.has_audio:
        saved_user_text = texts.AUDIO_HISTORY_TEMPLATE.format(
            transcribed_text=transcribed_text
        )

        if message.caption:
            saved_user_text = f"{message.caption}\n\n{saved_user_text}"

    elif info.has_media:
        if info.media_type in ("tgs", "webm", "gif", "mp4"):
            saved_user_text = texts.ANIMATION_HISTORY_TEMPLATE.format(
                media_type=info.media_type
            )

        elif message.photo:
            saved_user_text = texts.PHOTO_HISTORY_TEXT

        elif message.sticker:
            saved_user_text = texts.STICKER_HISTORY_TEXT

        else:
            saved_user_text = texts.IMAGE_HISTORY_TEXT

        if message.caption:
            saved_user_text += f" {message.caption}"

    elif info.has_document:
        # has_document is only set when the message carries a document.
        document = cast("Document", info.document)

        saved_user_text = texts.DOCUMENT_HISTORY_TEMPLATE.format(
            filename=document.file_name or "document",
            document_format=cast("str", document_format).upper(),
        )

        if message.caption:
            saved_user_text += f" {message.caption}"

    else:
        saved_user_text = text_override if text_override is not None else message.text

    return saved_user_text
