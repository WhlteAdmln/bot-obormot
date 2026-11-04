"""Сборка содержимого входящего сообщения для LLM."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from bot.errors import DocumentTooLongError
from bot.services.chat.input.models import MessageInfo
from bot.services.validation import MAX_INPUT_TEXT_LENGTH, validate_input_text

if TYPE_CHECKING:
    from aiogram.types import Message


def build_user_content(
    message: Message,
    info: MessageInfo,
    *,
    text_override: str | None,
    transcribed_text: str | None,
    image_urls: list[str] | None,
    document_text: str | None,
    document_format: str | None,
):
    """Формирует текстовое или мультимодальное содержимое для LLM."""

    if info.has_audio:
        user_content = transcribed_text

        if message.caption:
            user_content = (
                f"{message.caption}\n\n[Распознанная речь]: {transcribed_text}"
            )

    elif info.has_media:
        from bot.services.media import get_user_content

        user_content = get_user_content(
            message,
            image_urls,
            info.media_type,
        )

    elif info.has_document:
        document = info.document
        raw_name = document.file_name or "document"
        safe_name = re.sub(r"[\r\n\[\]]+", " ", raw_name)[:100]

        user_content = f"[Содержимое документа: {safe_name}]\n\n{document_text}"

        if message.caption:
            user_content = f"{message.caption}\n\n{user_content}"

        if len(user_content) > MAX_INPUT_TEXT_LENGTH:
            raise DocumentTooLongError("Document message exceeds 8000 characters")

    else:
        user_content = text_override if text_override is not None else message.text

    if isinstance(user_content, str):
        validate_input_text(user_content)

    return user_content
