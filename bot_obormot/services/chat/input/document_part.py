# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Download documents and extract their text."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from bot_obormot.common.text import log_safe
from bot_obormot.errors import DocumentAPIError, DocumentTooLongError
from bot_obormot.services.documents import process_document
from bot_obormot.settings import Settings, get_settings

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from aiogram.types import Document, Message

    from bot_obormot.services.chat.input.models import MessageInfo
    from bot_obormot.services.documents.response import DocumentResponse

logger = logging.getLogger("bot_obormot.services.chat.input.document_part")


async def prepare_document(
    message: Message,
    info: MessageInfo,
    *,
    downloader: Callable[..., Awaitable[bytes]],
    document_processor: Callable[..., Awaitable[DocumentResponse]] | None = None,
    settings: Settings | None = None,
) -> tuple[str, str]:
    """Download a document and retrieve its extracted text."""
    if settings is None:
        settings = get_settings()

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

    # The branches call different signatures, so a ternary would not read well.
    if document_processor is None:  # pylint: disable=consider-ternary-expression
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
