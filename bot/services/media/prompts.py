# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Default text prompts for media messages."""

from aiogram.types import Message


def get_media_prompt(message: Message, media_type: str | None) -> str:
    """Формирует текстовую часть мультимодального запроса."""
    if message.caption:
        return message.caption

    if media_type in ("tgs", "webm", "gif", "mp4"):
        return (
            "Посмотри на последовательность кадров этой анимации. "
            "Опиши, что происходит, какие движения и эмоции "
            "ты замечаешь."
        )

    if message.sticker:
        return "Посмотри на стикер и опиши его."

    return "Посмотри на изображение и опиши, что на нём изображено."
