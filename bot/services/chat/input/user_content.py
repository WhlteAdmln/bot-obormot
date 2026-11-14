# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Сборка содержимого входящего сообщения для LLM."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, cast

from bot.errors import DocumentTooLongError
from bot.services.media import get_user_content
from bot.services.validation import MAX_INPUT_TEXT_LENGTH, validate_input_text

if TYPE_CHECKING:
    from aiogram.types import Document, Message

    from bot.services.chat.input.models import MessageInfo


def build_user_content(
    message: Message,
    info: MessageInfo,
    *,
    text_override: str | None,
    transcribed_text: str | None,
    image_urls: list[str] | None,
    document_text: str | None,
) -> str | list[dict[str, Any]] | None:
    """Формирует текстовое или мультимодальное содержимое для LLM."""
    user_content: str | list[dict[str, Any]] | None

    if info.has_audio:
        user_content = transcribed_text

        if message.caption:
            user_content = (
                f"{message.caption}\n\n[Распознанная речь]: {transcribed_text}"
            )

    elif info.has_media:
        user_content = get_user_content(
            message,
            image_urls,
            info.media_type,
        )

    elif info.has_document:
        # has_document is only set when the message carries a document.
        document = cast("Document", info.document)
        raw_name = document.file_name or "document"
        safe_name = re.sub(r"[\r\n\[\]]+", " ", raw_name)[:100]

        user_content = f"[Содержимое документа: {safe_name}]\n\n{document_text}"

        if message.caption:
            user_content = f"{message.caption}\n\n{user_content}"

        if len(user_content) > MAX_INPUT_TEXT_LENGTH:
            msg = f"Document message exceeds {MAX_INPUT_TEXT_LENGTH} characters"
            raise DocumentTooLongError(msg)

    else:
        user_content = text_override if text_override is not None else message.text

    if isinstance(user_content, str):
        validate_input_text(user_content)

    return user_content
