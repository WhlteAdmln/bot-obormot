# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Подготовка фото, стикеров и анимаций для мультимодального запроса."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, cast

from bot.services.media import process_media

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import Message

    from bot.services.chat.input.models import MessageInfo


async def prepare_media(
    message: Message,
    info: MessageInfo,
    *,
    media_processor: Callable[..., Awaitable[list[str]]] | None = None,
) -> tuple[list[str], list[bytes]]:
    """Обрабатывает Telegram-медиа и декодирует полученные Data URL."""
    if media_processor is None:
        media_processor = process_media

    image_urls = await media_processor(
        message,
        cast("str", info.media_type),
        cast("str", info.file_id),
    )

    image_bytes = [base64.b64decode(url.split(",", 1)[1]) for url in image_urls]
    return image_urls, image_bytes
