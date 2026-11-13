# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Скачивание и извлечение текста из документов."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from bot.errors import DocumentAPIError, DocumentTooLongError
from bot.services.documents import process_document
from bot.services.telegram.downloader import download_telegram_file
from bot.utils.text import log_safe

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import Message

    from bot.services.chat.input.models import MessageInfo

logger = logging.getLogger("bot.services.chat.input.document_part")


async def prepare_document(
    message: Message,
    info: MessageInfo,
    *,
    downloader: Callable[..., Awaitable[bytes]] | None = None,
    document_processor: Callable[..., Awaitable[dict[str, Any]]] | None = None,
) -> tuple[str, str]:
    """Скачивает документ и получает извлечённый текст."""
    if downloader is None:
        downloader = download_telegram_file

    if document_processor is None:
        document_processor = process_document

    document = info.document

    logger.info(
        "DOCUMENT: начинаю скачивание: %s",
        log_safe(document.file_name),
    )

    document_data = await downloader(
        message,
        document.file_id,
    )

    logger.info(
        "DOCUMENT: файл скачан, размер: %s байт",
        len(document_data),
    )

    result = await document_processor(
        document_data,
        document.file_name or "document",
    )

    if result.get("truncated", False) is True:
        raise DocumentTooLongError

    document_text = result["text"]
    document_format = result["format"]

    if not document_text.strip():
        raise DocumentAPIError(
            422,
            "Document contains no extractable text",
        )

    logger.info(
        "DOCUMENT: обработка завершена, формат=%s, символов=%s",
        document_format,
        len(document_text),
    )

    return document_text, document_format
