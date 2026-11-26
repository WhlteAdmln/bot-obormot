# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build incoming message content for the LLM."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, cast

from bot_obormot.common.validation import MAX_INPUT_TEXT_LENGTH, validate_input_text
from bot_obormot.errors import DocumentTooLongError
from bot_obormot.services.chat.input import texts
from bot_obormot.services.media import get_user_content

if TYPE_CHECKING:
    from aiogram.types import Document, Message

    from bot_obormot.common.llm_messages import ContentPart
    from bot_obormot.services.chat.input.models import MessageInfo


def _audio_content(message: Message, transcribed_text: str | None) -> str | None:
    """Return the transcript, framed by the caption when the message has one."""
    if message.caption:
        return texts.RECOGNIZED_SPEECH_TEMPLATE.format(
            caption=message.caption,
            transcribed_text=transcribed_text,
        )

    return transcribed_text


def _document_content(
    message: Message,
    info: MessageInfo,
    document_text: str | None,
) -> str:
    """Return the document text with its sanitized name and the caption."""
    # has_document is only set when the message carries a document.
    document = cast("Document", info.document)
    raw_name = document.file_name or "document"
    safe_name = re.sub(r"[\r\n\[\]]+", " ", raw_name)[:100]

    content = texts.DOCUMENT_CONTENT_TEMPLATE.format(
        filename=safe_name,
        document_text=document_text,
    )

    if message.caption:
        content = f"{message.caption}\n\n{content}"

    if len(content) > MAX_INPUT_TEXT_LENGTH:
        msg = f"Document message exceeds {MAX_INPUT_TEXT_LENGTH} characters"
        raise DocumentTooLongError(msg)

    return content


def _select_content(
    message: Message,
    info: MessageInfo,
    text_override: str | None,
    transcribed_text: str | None,
    image_urls: list[str] | None,
    document_text: str | None,
) -> str | list[ContentPart] | None:
    """Pick the content that matches the kind of message."""
    if info.has_audio:
        return _audio_content(message, transcribed_text)

    if info.has_media:
        return get_user_content(message, image_urls, info.media_type)

    if info.has_document:
        return _document_content(message, info, document_text)

    return text_override if text_override is not None else message.text


def build_user_content(
    message: Message,
    info: MessageInfo,
    *,
    text_override: str | None,
    transcribed_text: str | None,
    image_urls: list[str] | None,
    document_text: str | None,
) -> str | list[ContentPart] | None:
    """Build text or multimodal content for the LLM."""
    user_content = _select_content(
        message, info, text_override, transcribed_text, image_urls, document_text
    )

    if isinstance(user_content, str):
        validate_input_text(user_content)

    return user_content
