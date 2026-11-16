# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Download documents and extract their text."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from bot.common.text import log_safe
from bot.errors import DocumentAPIError, DocumentTooLongError
from bot.services.documents import process_document
from bot.services.telegram.downloader import download_telegram_file
from bot.settings import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import Document, Message

    from bot.services.chat.input.models import MessageInfo

logger = logging.getLogger("bot.services.chat.input.document_part")


async def prepare_document(
    message: Message,
    info: MessageInfo,
    *,
    downloader: Callable[..., Awaitable[bytes]] | None = None,
    document_processor: Callable[..., Awaitable[dict[str, Any]]] | None = None,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """Download a document and retrieve its extracted text."""
    if settings is None:
        settings = get_settings()

    if downloader is None:
        downloader = download_telegram_file

    # has_document is only set when the message carries a document.
    document = cast("Document", info.document)

    logger.info(
        "DOCUMENT: starting download: %s",
        log_safe(document.file_name),
    )

    document_data = await downloader(
        message,
        document.file_id,
    )

    logger.info(
        "DOCUMENT: file downloaded, size: %s bytes",
        len(document_data),
    )

    if document_processor is None:
        result = await process_document(
            document_data,
            document.file_name or "document",
            settings=settings,
        )
    else:
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
        "DOCUMENT: processing completed, format=%s, characters=%s",
        document_format,
        len(document_text),
    )

    return document_text, document_format
