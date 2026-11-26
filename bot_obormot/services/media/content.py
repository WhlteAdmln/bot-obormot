# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build multimodal message content for the LLM."""

from aiogram.types import Message

from bot_obormot.common.llm_messages import ContentPart
from bot_obormot.services.media.prompts import get_media_prompt
from bot_obormot.services.media.texts import (
    ANIMATION_CONTACT_SHEET_INSTRUCTION,
    MULTIPLE_FRAMES_INSTRUCTION,
)


def get_user_content(
    message: Message,
    image_urls: list[str] | None,
    media_type: str | None,
) -> str | list[ContentPart] | None:
    """Build a multimodal message for the LLM."""
    if not image_urls:
        return message.text

    prompt = get_media_prompt(message, media_type)

    if media_type in {"tgs", "webm", "gif", "mp4"}:
        prompt += ANIMATION_CONTACT_SHEET_INSTRUCTION
    elif len(image_urls) > 1:
        prompt += MULTIPLE_FRAMES_INSTRUCTION

    content: list[ContentPart] = [{"type": "text", "text": prompt}]
    content.extend(
        {"type": "image_url", "image_url": {"url": image_url}}
        for image_url in image_urls
    )

    return content
