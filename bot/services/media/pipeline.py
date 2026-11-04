import asyncio
import logging

from aiogram.types import Message

from bot.errors import MediaError
from bot.services.media.animation import extract_animation_frames
from bot.services.media.images import prepare_image
from bot.services.telegram.downloader import download_telegram_file

logger = logging.getLogger("bot.services.media")


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

    try:
        if media_type == "image":
            return [await asyncio.to_thread(image_preparer, data)]

        frames = await animation_extractor(data, media_type)

        return await asyncio.gather(
            *(asyncio.to_thread(image_preparer, frame) for frame in frames)
        )

    except MediaError:
        raise

    except Exception as error:
        logger.exception(
            "Failed to prepare media for LLM: media_type=%s",
            media_type,
        )
        raise MediaError(f"Failed to prepare {media_type} media") from error
