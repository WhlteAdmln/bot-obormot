import asyncio
import logging

from aiogram.types import Message

from bot.errors import MediaError
from bot.services.media.animation import extract_animation_frames
from bot.services.media.images import prepare_image
from bot.services.media.limits import MAX_CONCURRENT_IMAGE_JOBS
from bot.services.media.sniff import verify_declared_type
from bot.services.telegram.downloader import download_telegram_file

logger = logging.getLogger("bot.services.media")
_image_jobs = asyncio.Semaphore(MAX_CONCURRENT_IMAGE_JOBS)


async def _run_limited(func, *args):
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


async def process_media(
    message: Message,
    media_type: str,
    file_id: str,
    *,
    downloader=download_telegram_file,
    animation_extractor=extract_animation_frames,
    image_preparer=prepare_image,
) -> list[str]:
    """Скачивает и преобразует медиа в изображения для LLM."""

    data = await downloader(message, file_id)
    verify_declared_type(data, media_type)

    try:
        if media_type == "image":
            return [await _run_limited(image_preparer, data)]

        frames = await animation_extractor(data, media_type)

        return await asyncio.gather(
            *(_run_limited(image_preparer, frame) for frame in frames)
        )

    except MediaError:
        raise

    except Exception as error:
        logger.exception(
            "Failed to prepare media for LLM: media_type=%s",
            media_type,
        )
        raise MediaError(f"Failed to prepare {media_type} media") from error
