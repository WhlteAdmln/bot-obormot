"""Сценарии чтения и сброса истории диалога."""

import asyncio
import logging
from pathlib import Path
from typing import Callable

import aiosqlite

from bot.services.database.files.image_storage import is_managed_image
from bot.services.database.repositories import messages

ImageReader = Callable[[Path, str], str]
ImageDeleter = Callable[[Path], None]


async def get_history(
    connection: aiosqlite.Connection,
    user_id: int,
    limit: int | None,
    max_images: int,
    read_image_as_base64: ImageReader,
    logger: logging.Logger,
) -> list[dict]:
    """Собирает полные обмены в формат сообщений LLM."""
    max_images = max(0, max_images)
    exchange_limit = -1 if limit is None else max(0, limit)
    rows = await messages.fetch_history_rows(
        connection,
        user_id,
        exchange_limit,
        max_images,
    )

    history = []
    current_id = None
    current_role = None
    current_content = None
    image_parts = []

    def save_current_message():
        if current_id is None:
            return

        if image_parts:
            content = [
                {
                    "type": "text",
                    "text": current_content,
                },
                *image_parts,
            ]
        else:
            content = current_content

        history.append(
            {
                "role": current_role,
                "content": content,
            }
        )

    for row in rows:
        message_id = row["id"]

        if message_id != current_id:
            save_current_message()
            current_id = message_id
            current_role = row["role"]
            current_content = row["content"]
            image_parts = []

        file_path = row["file_path"]
        if not file_path:
            continue

        image_path = Path(file_path)
        mime_type = row["mime_type"] or "image/jpeg"

        try:
            data_url = await asyncio.to_thread(
                read_image_as_base64,
                image_path,
                mime_type,
            )
            image_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": data_url,
                    },
                }
            )
        except FileNotFoundError:
            logger.warning("History image not found: %s", image_path)
        except OSError:
            logger.exception("Could not read history image: %s", image_path)

    save_current_message()
    return history


async def reset_history(
    connection: aiosqlite.Connection,
    user_id: int,
    delete_image: ImageDeleter,
    logger: logging.Logger,
    images_dir: Path | None = None,
) -> None:
    """Удаляет историю пользователя и связанные файлы изображений."""
    rows = await messages.fetch_user_media_paths(connection, user_id)
    await messages.delete_user_messages(connection, user_id)

    for row in rows:
        image_path = Path(row["file_path"])

        if images_dir is not None and not is_managed_image(image_path, images_dir):
            logger.warning("Skipping image outside images directory: %s", image_path)
            continue

        try:
            await asyncio.to_thread(delete_image, image_path)
        except OSError:
            logger.exception(
                "Could not remove image during history reset: %s",
                image_path,
            )
