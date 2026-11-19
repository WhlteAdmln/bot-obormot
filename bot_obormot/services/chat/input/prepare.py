# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Coordinate preparation of text, media, audio, and documents."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from bot_obormot.services.chat.input.audio_part import prepare_audio
from bot_obormot.services.chat.input.document_part import prepare_document
from bot_obormot.services.chat.input.media_part import prepare_media
from bot_obormot.services.chat.input.models import MessageInfo, PreparedMessage
from bot_obormot.services.chat.input.saved_text import build_saved_user_text
from bot_obormot.services.chat.input.user_content import build_user_content
from bot_obormot.settings import Settings, get_settings

if TYPE_CHECKING:
    from aiogram.types import Message

logger = logging.getLogger("bot_obormot.services.chat.input.prepare")


async def prepare_message(
    message: Message,
    info: MessageInfo,
    text_override: str | None = None,
    settings: Settings | None = None,
) -> PreparedMessage:
    """Download and process incoming content."""
    if settings is None:
        settings = get_settings()

    image_urls: list[str] | None = None
    image_bytes: list[bytes] | None = None
    transcribed_text: str | None = None
    document_text: str | None = None
    document_format: str | None = None

    # The processing order is intentional: audio, media, then document.
    if info.has_audio:
        transcribed_text = await prepare_audio(message, info, settings=settings)

    if info.has_media:
        image_urls, image_bytes = await prepare_media(message, info)

    if info.has_document:
        document_text, document_format = await prepare_document(
            message, info, settings=settings
        )

    user_content = build_user_content(
        message,
        info,
        text_override=text_override,
        transcribed_text=transcribed_text,
        image_urls=image_urls,
        document_text=document_text,
    )

    saved_user_text = build_saved_user_text(
        message,
        info,
        text_override=text_override,
        transcribed_text=transcribed_text,
        document_format=document_format,
    )

    # PreparedMessage keeps its historical annotations; the values are passed
    # through unchanged, so only the static type is narrowed here.
    return PreparedMessage(
        user_content=cast("str", user_content),
        saved_user_text=cast("str", saved_user_text),
        image_bytes=image_bytes,
    )
