# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Default text prompts for media messages."""

from aiogram.types import Message

from bot.services.media.texts import (
    ANIMATION_MEDIA_PROMPT,
    IMAGE_MEDIA_PROMPT,
    STICKER_MEDIA_PROMPT,
)


def get_media_prompt(message: Message, media_type: str | None) -> str:
    """Build the text portion of a multimodal request."""
    if message.caption:
        return message.caption

    if media_type in ("tgs", "webm", "gif", "mp4"):
        return ANIMATION_MEDIA_PROMPT

    if message.sticker:
        return STICKER_MEDIA_PROMPT

    return IMAGE_MEDIA_PROMPT
