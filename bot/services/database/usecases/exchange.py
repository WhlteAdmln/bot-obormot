# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Сценарий атомарного сохранения обмена сообщениями и изображений."""

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from bot.errors import DatabaseError, MediaError
from bot.services.database.files.image_storage import delete_image, save_image


@dataclass(frozen=True)
class ExchangeContext:
    """Dependencies required to persist a message exchange."""

    connection: aiosqlite.Connection
    lock: asyncio.Lock
    images_dir: Path
    logger: logging.Logger


async def _persist_exchange(
    context: ExchangeContext,
    user_id: int,
    user_text: str,
    assistant_text: str,
    saved_files: list[Path],
) -> None:
    """Persists the messages and media in one transaction."""
    async with context.lock:
        transaction_started = False
        try:
            await context.connection.execute("BEGIN IMMEDIATE")
            transaction_started = True

            cursor = await context.connection.execute(
                """
                INSERT INTO messages(user_id, role, content)
                VALUES (?, 'user', ?)
                """,
                (user_id, user_text),
            )
            user_message_id = cursor.lastrowid

            for image_path in saved_files:
                await context.connection.execute(
                    """
                    INSERT INTO message_media(
                        message_id,
                        file_path,
                        mime_type
                    )
                    VALUES (?, ?, 'image/jpeg')
                    """,
                    (user_message_id, str(image_path)),
                )

            await context.connection.execute(
                """
                INSERT INTO messages(user_id, role, content)
                VALUES (?, 'assistant', ?)
                """,
                (user_id, assistant_text),
            )

            await context.connection.commit()
            transaction_started = False

        except Exception:
            if transaction_started:
                try:
                    await context.connection.rollback()
                except aiosqlite.Error:
                    context.logger.exception("Database rollback failed")
            raise


async def _remove_saved_files(
    context: ExchangeContext,
    saved_files: list[Path],
) -> None:
    """Removes saved images after a failed exchange."""
    for image_path in saved_files:
        try:
            await asyncio.to_thread(delete_image, image_path)
        except OSError:
            context.logger.exception(
                "Could not remove image after failed exchange: %s",
                image_path,
            )


async def add_exchange(
    context: ExchangeContext,
    user_id: int,
    user_text: str,
    *,
    assistant_text: str,
    media: list[bytes] | None,
) -> None:
    """Атомарно сохраняет пару сообщений и связанные изображения.

    Блокировка передаётся фасадом и захватывается только на уровне сценария
    транзакции; репозитории не управляют конкурентным доступом к соединению.
    """
    saved_files: list[Path] = []

    try:
        # Save images without blocking the event loop.
        for image_data in media or []:
            filename = f"{uuid.uuid4().hex}.jpg"
            image_path = context.images_dir / filename
            saved_files.append(image_path)
            await asyncio.to_thread(save_image, image_path, image_data)

        await _persist_exchange(
            context,
            user_id,
            user_text,
            assistant_text,
            saved_files,
        )

    except Exception as error:
        # Compensate for a failed write by deleting saved files.
        await _remove_saved_files(context, saved_files)

        if isinstance(error, aiosqlite.Error):
            context.logger.exception("Could not save message exchange")
            msg = "Could not save message exchange"
            raise DatabaseError(msg) from error

        if isinstance(error, OSError):
            msg = "Could not save or remove media file"
            raise MediaError(msg) from error

        raise
