# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Client for the Document Engine (audiodoc) API."""

import json
import logging
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from bot.errors import (
    DocumentAPIError,
    DocumentTimeoutError,
    DocumentUnavailableError,
)
from bot.services.documents.response import validate_document_response
from bot.services.http_limits import (
    MAX_ERROR_BODY_BYTES,
    MAX_SERVICE_RESPONSE_BYTES,
    read_limited_body,
)
from bot.services.validation import MAX_INPUT_TEXT_LENGTH
from bot.settings import Settings, get_settings
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)


def _endpoint_url(base_url: str, endpoint: str) -> str:
    parts = urlsplit(base_url)
    path = f"{parts.path.rstrip('/')}/{endpoint}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


# Reserve room for the document label, filename, and an optional Telegram caption.
DOCUMENT_TEXT_OVERHEAD_RESERVE = 1024
MAX_DOCUMENT_TEXT_LENGTH = MAX_INPUT_TEXT_LENGTH - DOCUMENT_TEXT_OVERHEAD_RESERVE


async def process_document(
    document_data: bytes,
    filename: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Отправляет документ в Document Engine и возвращает результат."""
    if settings is None:
        settings = get_settings()

    if not settings.AUDIODOC_URL:
        msg = "AUDIODOC_URL is not configured"
        raise DocumentUnavailableError(msg)

    filename = Path(filename or "document").name
    # The name is copied into a multipart header as well as the log.
    # Escape control characters before aiohttp constructs Content-Disposition.
    safe_filename = log_safe(filename, limit=255)

    form = aiohttp.FormData()
    form.add_field(
        "file",
        document_data,
        filename=safe_filename,
        content_type="application/octet-stream",
    )
    form.add_field("max_characters", str(MAX_DOCUMENT_TEXT_LENGTH))

    timeout = aiohttp.ClientTimeout(total=settings.AUDIODOC_DOCUMENT_TIMEOUT)
    headers = (
        {"Authorization": f"Bearer {settings.AUDIODOC_DOCUMENT_KEY}"}
        if settings.AUDIODOC_DOCUMENT_KEY
        else {}
    )

    try:
        logger.info(
            "Sending document: filename=%s, size=%s",
            safe_filename,
            len(document_data),
        )

        async with (
            aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session,
            session.post(
                _endpoint_url(settings.AUDIODOC_URL, "process-document"),
                data=form,
            ) as response,
        ):
            if response.status != HTTPStatus.OK:
                body = await read_limited_body(response, MAX_ERROR_BODY_BYTES)
                detail = (body or b"").decode("utf-8", errors="replace")

                raise DocumentAPIError(
                    response.status,
                    detail[:1000],
                )

            body = await read_limited_body(response, MAX_SERVICE_RESPONSE_BYTES)

            if body is None:
                raise DocumentAPIError(
                    502,
                    "Document Engine response is too large",
                )

            try:
                result = json.loads(body)
            except ValueError as error:
                raise DocumentAPIError(
                    502,
                    "Document Engine returned invalid JSON",
                ) from error

        result = validate_document_response(result)

        logger.info(
            "Document processed: filename=%s, format=%s, characters=%s",
            safe_filename,
            result["format"],
            result["characters"],
        )

    except TimeoutError as error:
        msg = "Document processing timed out"
        raise DocumentTimeoutError(msg) from error

    except aiohttp.ClientError as error:
        msg = f"Document Engine connection error: {error}"
        raise DocumentUnavailableError(msg) from error

    else:
        return result
