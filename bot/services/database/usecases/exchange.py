# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Сценарий атомарного сохранения обмена сообщениями и изображений."""

import asyncio
import logging
import uuid
from pathlib import Path

import aiosqlite

from bot.errors import DatabaseError, MediaError
from bot.services.database.files.image_storage import delete_image, save_image


async def add_exchange(
    connection: aiosqlite.Connection,
    lock: asyncio.Lock,
    images_dir: Path,
    user_id: int,
    user_text: str,
    assistant_text: str,
    media: list[bytes] | None,
    logger: logging.Logger,
) -> None:
    """Атомарно сохраняет пару сообщений и связанные изображения.

    Блокировка передаётся фасадом и захватывается только на уровне сценария
    транзакции; репозитории не управляют конкурентным доступом к соединению.
    """
    saved_files: list[Path] = []

    try:
        # Сохраняем изображения, не блокируя event loop.
        for image_data in media or []:
            filename = f"{uuid.uuid4().hex}.jpg"
            image_path = images_dir / filename
            saved_files.append(image_path)
            await asyncio.to_thread(save_image, image_path, image_data)

        # Защищаем всю транзакцию и использование общего соединения.
        async with lock:
            transaction_started = False
            try:
                await connection.execute("BEGIN IMMEDIATE")
                transaction_started = True

                cursor = await connection.execute(
                    """
                    INSERT INTO messages(user_id, role, content)
                    VALUES (?, 'user', ?)
                    """,
                    (user_id, user_text),
                )
                user_message_id = cursor.lastrowid

                for image_path in saved_files:
                    await connection.execute(
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

                await connection.execute(
                    """
                    INSERT INTO messages(user_id, role, content)
                    VALUES (?, 'assistant', ?)
                    """,
                    (user_id, assistant_text),
                )

                await connection.commit()
                transaction_started = False

            except Exception:
                if transaction_started:
                    try:
                        await connection.rollback()
                    except aiosqlite.Error:
                        logger.exception("Database rollback failed")
                raise

    except Exception as error:
        # Компенсируем неудачную запись удалением уже сохранённых файлов.
        for image_path in saved_files:
            try:
                await asyncio.to_thread(delete_image, image_path)
            except OSError:
                logger.exception(
                    "Could not remove image after failed exchange: %s",
                    image_path,
                )

        if isinstance(error, aiosqlite.Error):
            logger.exception("Could not save message exchange")
            msg = "Could not save message exchange"
            raise DatabaseError(msg) from error

        if isinstance(error, OSError):
            msg = "Could not save or remove media file"
            raise MediaError(msg) from error

        raise
