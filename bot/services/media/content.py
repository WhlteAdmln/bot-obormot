# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Construction of multimodal message content for the LLM."""

from typing import Any

from aiogram.types import Message

from bot.services.media.prompts import get_media_prompt


def get_user_content(
    message: Message,
    image_urls: list[str] | None,
    media_type: str | None,
) -> str | list[dict[str, Any]] | None:
    """Формирует мультимодальное сообщение для LLM."""
    if not image_urls:
        return message.text

    prompt = get_media_prompt(message, media_type)

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

    if media_type in ("tgs", "webm", "gif", "mp4"):
        content[0]["text"] += (
            "\n\nКадры собраны в одно нумерованное изображение-монтаж. "
            "Просматривай их по порядку: слева направо, сверху вниз, "
            "и рассматривай как последовательность одной анимации."
        )
    elif len(image_urls) > 1:
        content[0]["text"] += (
            "\n\nКадры расположены в хронологическом порядке. "
            "Рассматривай их как последовательность одной анимации."
        )

    content.extend(
        {"type": "image_url", "image_url": {"url": image_url}}
        for image_url in image_urls
    )

    return content
