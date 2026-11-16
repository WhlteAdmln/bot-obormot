# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build multimodal message content for the LLM."""

from typing import Any

from aiogram.types import Message

from bot.services.media.prompts import get_media_prompt
from bot.services.media.texts import (
    ANIMATION_CONTACT_SHEET_INSTRUCTION,
    MULTIPLE_FRAMES_INSTRUCTION,
)


def get_user_content(
    message: Message,
    image_urls: list[str] | None,
    media_type: str | None,
) -> str | list[dict[str, Any]] | None:
    """Build a multimodal message for the LLM."""
    if not image_urls:
        return message.text

    prompt = get_media_prompt(message, media_type)

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

    if media_type in ("tgs", "webm", "gif", "mp4"):
        content[0]["text"] += ANIMATION_CONTACT_SHEET_INSTRUCTION
    elif len(image_urls) > 1:
        content[0]["text"] += MULTIPLE_FRAMES_INSTRUCTION

    content.extend(
        {"type": "image_url", "image_url": {"url": image_url}}
        for image_url in image_urls
    )

    return content
