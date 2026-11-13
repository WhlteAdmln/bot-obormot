# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Сценарии чтения и сброса истории диалога."""

import asyncio
import base64
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import aiosqlite

from bot.services.database.files.image_storage import is_managed_image
from bot.services.database.repositories import messages
from bot.services.media.contact_sheet import build_contact_sheet

ImageReader = Callable[[Path, str], str]
ImageDeleter = Callable[[Path], None]


def _decode_data_url(data_url: str) -> bytes:
    """Decodes the base64 payload of an image data URL."""
    _header, separator, encoded = data_url.partition(",")
    if not separator:
        msg = "Invalid image data URL in history"
        raise ValueError(msg)
    return base64.b64decode(encoded, validate=True)


async def get_history(
    connection: aiosqlite.Connection,
    user_id: int,
    limit: int | None,
    max_images: int,
    read_image_as_base64: ImageReader,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """Собирает обмены для LLM; max_images ограничивает медиа-сообщения."""
    max_images = max(0, max_images)
    exchange_limit = -1 if limit is None else max(0, limit)
    rows = await messages.fetch_history_rows(
        connection,
        user_id,
        exchange_limit,
        max_images,
    )

    history: list[dict[str, Any]] = []
    current_id: int | None = None
    current_role: str | None = None
    current_content: str | None = None
    image_parts: list[dict[str, Any]] = []

    def save_current_message() -> None:
        if current_id is None:
            return

        message_image_parts = list(image_parts)
        if len(message_image_parts) > 1:
            # Старые версии сохраняли каждый кадр анимации отдельным файлом.
            # При чтении истории сводим такие кадры в один монтаж, чтобы не
            # раздувать число image_url и не терять связь между кадрами.
            try:
                frame_data = [
                    _decode_data_url(part["image_url"]["url"])
                    for part in message_image_parts
                ]

                contact_sheet = build_contact_sheet(frame_data)
                encoded_sheet = base64.b64encode(contact_sheet).decode("ascii")
                message_image_parts = [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded_sheet}"},
                    }
                ]
            except Exception:
                logger.exception(
                    "Could not combine historical animation frames: message_id=%s",
                    current_id,
                )

        content: str | list[dict[str, Any]] | None
        if message_image_parts:
            content = [
                {
                    "type": "text",
                    "text": current_content,
                },
                *message_image_parts,
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
