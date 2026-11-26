# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Use cases for reading and resetting conversation history."""

import asyncio
import base64
import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import aiosqlite

from bot_obormot.common.llm_messages import (
    ChatMessage,
    ImageURLPart,
    MessageContent,
)
from bot_obormot.services.database.files.image_storage import is_managed_image
from bot_obormot.services.database.repositories import messages
from bot_obormot.services.media.contact_sheet import build_contact_sheet

ImageReader = Callable[[Path, str], str]
ImageDeleter = Callable[[Path], None]


def _decode_data_url(data_url: str) -> bytes:
    """Decodes the base64 payload of an image data URL."""
    _header, separator, encoded = data_url.partition(",")
    if not separator:
        msg = "Invalid image data URL in history"
        raise ValueError(msg)
    return base64.b64decode(encoded, validate=True)


def _combine_animation_frames(
    image_parts: list[ImageURLPart],
) -> list[ImageURLPart]:
    """Merge image parts into a single contact-sheet image part."""
    frame_data = [_decode_data_url(part["image_url"]["url"]) for part in image_parts]
    contact_sheet = build_contact_sheet(frame_data)
    encoded_sheet = base64.b64encode(contact_sheet).decode("ascii")
    return [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encoded_sheet}"},
        }
    ]


def _build_history_message_content(
    message_id: int,
    current_content: str,
    image_parts: list[ImageURLPart],
    logger: logging.Logger,
) -> MessageContent:
    message_image_parts = list(image_parts)
    if len(message_image_parts) > 1:
        # Older versions stored each animation frame as a separate file.
        # Combine frames into one contact sheet when reading history.
        try:
            message_image_parts = _combine_animation_frames(message_image_parts)
        except Exception:
            logger.exception(
                "Could not combine historical animation frames: message_id=%s",
                message_id,
            )

    if message_image_parts:
        return [
            {
                "type": "text",
                "text": current_content,
            },
            *message_image_parts,
        ]
    return current_content


@dataclass
class _PendingMessage:
    """A history message whose image parts are still being collected."""

    message_id: int
    role: str
    content: str
    image_parts: list[ImageURLPart] = field(default_factory=list)


def _append_history_message(
    history: list[ChatMessage],
    pending: _PendingMessage | None,
    logger: logging.Logger,
) -> None:
    if pending is None:
        return
    history.append(
        {
            "role": pending.role,
            "content": _build_history_message_content(
                pending.message_id,
                pending.content,
                pending.image_parts,
                logger,
            ),
        }
    )


async def _read_image_part(
    row: sqlite3.Row,
    read_image_as_base64: ImageReader,
    logger: logging.Logger,
) -> ImageURLPart | None:
    """Read one stored image as an image part, or None when it is unavailable."""
    file_path = row["file_path"]
    if not file_path:
        return None

    image_path = Path(file_path)
    mime_type = row["mime_type"] or "image/jpeg"

    try:
        data_url = await asyncio.to_thread(
            read_image_as_base64,
            image_path,
            mime_type,
        )
    except FileNotFoundError:
        logger.warning("History image not found: %s", image_path)
    except OSError:
        logger.exception("Could not read history image: %s", image_path)
    else:
        return {"type": "image_url", "image_url": {"url": data_url}}
    return None


async def get_history(
    connection: aiosqlite.Connection,
    user_id: int,
    limit: int | None,
    max_images: int,
    read_image_as_base64: ImageReader,
    logger: logging.Logger,
) -> list[ChatMessage]:
    """Build exchanges for the LLM; max_images limits media messages."""
    max_images = max(0, max_images)
    exchange_limit = -1 if limit is None else max(0, limit)
    rows = await messages.fetch_history_rows(
        connection,
        user_id,
        exchange_limit,
        max_images,
    )

    history: list[ChatMessage] = []
    pending: _PendingMessage | None = None

    for row in rows:
        if pending is None or row["id"] != pending.message_id:
            _append_history_message(history, pending, logger)
            pending = _PendingMessage(row["id"], row["role"], row["content"])

        image_part = await _read_image_part(row, read_image_as_base64, logger)
        if image_part is not None:
            pending.image_parts.append(image_part)

    _append_history_message(history, pending, logger)
    return history


async def reset_history(
    connection: aiosqlite.Connection,
    user_id: int,
    delete_image: ImageDeleter,
    logger: logging.Logger,
    images_dir: Path | None = None,
) -> None:
    """Delete the user's history and associated image files."""
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
