# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Prepare audio and retrieve its transcription."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from bot.services.audio import transcribe_audio, validate_audio_duration
from bot.services.telegram.downloader import download_telegram_file
from bot.settings import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import Message

    from bot.services.chat.input.models import MessageInfo

logger = logging.getLogger("bot.services.chat.input.audio_part")


async def prepare_audio(
    message: Message,
    info: MessageInfo,
    *,
    duration_validator: Callable[..., object] | None = None,
    downloader: Callable[..., Awaitable[bytes]] | None = None,
    transcriber: Callable[..., Awaitable[str]] | None = None,
    settings: Settings | None = None,
) -> str:
    """Download audio and return the Whisper transcription."""
    if settings is None:
        settings = get_settings()

    if duration_validator is None:
        duration_validator = validate_audio_duration

    if downloader is None:
        downloader = download_telegram_file

    duration_validator(message)

    logger.info("AUDIO: starting download from Telegram")

    audio_data = await downloader(
        message,
        cast("str", info.audio_file_id),
    )

    logger.info(
        "AUDIO: file downloaded, size: %s bytes",
        len(audio_data),
    )

    logger.info("AUDIO: sending file to Whisper")

    if transcriber is None:
        transcribed_text = await transcribe_audio(
            audio_data,
            cast("str", info.audio_filename),
            settings=settings,
        )
    else:
        transcribed_text = await transcriber(
            audio_data,
            cast("str", info.audio_filename),
        )

    logger.info("AUDIO: recognized %d characters", len(transcribed_text))

    return transcribed_text
