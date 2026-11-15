# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Download and conversion of Telegram media into LLM-ready images."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from aiogram.types import Message

from bot.errors import MediaError
from bot.services.media.animation import extract_animation_frames
from bot.services.media.contact_sheet import build_contact_sheet
from bot.services.media.images import prepare_image
from bot.services.media.limits import MAX_CONCURRENT_IMAGE_JOBS
from bot.services.media.sniff import verify_declared_type
from bot.services.telegram.downloader import download_telegram_file

logger = logging.getLogger("bot.services.media")
_image_jobs = asyncio.Semaphore(MAX_CONCURRENT_IMAGE_JOBS)

_T = TypeVar("_T")

Downloader = Callable[[Message, str], Awaitable[bytes]]
AnimationExtractor = Callable[[bytes, str], Awaitable[list[bytes]]]
ImagePreparer = Callable[[bytes], str]
ContactSheetBuilder = Callable[[list[bytes]], bytes]


@dataclass(frozen=True)
class MediaPipelineOptions:
    """Dependencies for media downloading and image preparation."""

    downloader: Downloader = download_telegram_file
    animation_extractor: AnimationExtractor = extract_animation_frames
    image_preparer: ImagePreparer = prepare_image
    contact_sheet_builder: ContactSheetBuilder = build_contact_sheet


_DEFAULT_MEDIA_PIPELINE_OPTIONS: MediaPipelineOptions = MediaPipelineOptions()


async def _run_limited(func: Callable[..., _T], *args: object) -> _T:
    """Выполняет тяжёлую обработку изображения не более чем в N потоках."""
    async with _image_jobs:
        task = asyncio.create_task(asyncio.to_thread(func, *args))

        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Поток нельзя отменить: не освобождаем слот, пока он работает.
            try:
                await task
            finally:
                raise


def _ensure_frames(frames: list[bytes]) -> None:
    """Rejects an animation that produced no frames."""
    if not frames:
        msg = "Animation did not produce any frames"
        raise MediaError(msg)


async def process_media(
    message: Message,
    media_type: str,
    file_id: str,
    *,
    options: MediaPipelineOptions = _DEFAULT_MEDIA_PIPELINE_OPTIONS,
) -> list[str]:
    """Скачивает и преобразует медиа в изображения для LLM."""
    data = await options.downloader(message, file_id)
    verify_declared_type(data, media_type)

    try:
        if media_type == "image":
            return [await _run_limited(options.image_preparer, data)]

        frames = await options.animation_extractor(data, media_type)
        _ensure_frames(frames)

        # Передаём Vision-модели один монтаж с нумерованными кадрами,
        # а не несколько независимых image_url-частей.
        contact_sheet = await _run_limited(options.contact_sheet_builder, frames)
        prepared_image = await _run_limited(options.image_preparer, contact_sheet)

    except MediaError:
        raise

    except Exception as error:
        logger.exception(
            "Failed to prepare media for LLM: media_type=%s",
            media_type,
        )
        msg = f"Failed to prepare {media_type} media"
        raise MediaError(msg) from error

    else:
        return [prepared_image]
