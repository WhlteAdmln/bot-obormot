# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Client for the Document Engine (audiodoc) API."""

import logging
from http import HTTPStatus
from pathlib import Path
from typing import Any

import aiohttp

from bot_obormot.common.text import log_safe
from bot_obormot.common.validation import MAX_INPUT_TEXT_LENGTH
from bot_obormot.errors import (
    DocumentAPIError,
    DocumentTimeoutError,
    DocumentUnavailableError,
)
from bot_obormot.services.audiodoc_http import (
    bearer_headers,
    endpoint_url,
    file_form,
    post_form,
    require_base_url,
)
from bot_obormot.services.documents.response import validate_document_response
from bot_obormot.settings import Settings

logger = logging.getLogger(__name__)


# Reserve room for the document label, filename, and an optional Telegram caption.
DOCUMENT_TEXT_OVERHEAD_RESERVE = 1024
MAX_DOCUMENT_TEXT_LENGTH = MAX_INPUT_TEXT_LENGTH - DOCUMENT_TEXT_OVERHEAD_RESERVE


async def _post_document(
    url: str,
    form: aiohttp.FormData,
    client_timeout: aiohttp.ClientTimeout,
    headers: dict[str, str],
) -> object:
    """Post the document form and return the decoded JSON response."""
    response = await post_form(url, form, client_timeout, headers)
    if response.status != HTTPStatus.OK:
        raise DocumentAPIError(response.status, response.detail[:1000])

    if response.body is None:
        raise DocumentAPIError(
            502,
            "Document Engine response is too large",
        )

    try:
        return response.json()
    except ValueError as error:
        raise DocumentAPIError(
            502,
            "Document Engine returned invalid JSON",
        ) from error


async def process_document(
    document_data: bytes,
    filename: str,
    *,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Send a document to the Document Engine and return the result."""
    settings = require_base_url(settings, DocumentUnavailableError)

    filename = Path(filename or "document").name
    # The name is copied into a multipart header as well as the log.
    # Escape control characters before aiohttp constructs Content-Disposition.
    safe_filename = log_safe(filename, limit=255)

    form = file_form(document_data, safe_filename)
    form.add_field("max_characters", str(MAX_DOCUMENT_TEXT_LENGTH))

    timeout = aiohttp.ClientTimeout(total=settings.AUDIODOC_DOCUMENT_TIMEOUT)
    headers = bearer_headers(settings.AUDIODOC_DOCUMENT_KEY)

    logger.info(
        "Sending document: filename=%s, size=%s",
        safe_filename,
        len(document_data),
    )

    try:
        raw_result = await _post_document(
            endpoint_url(settings.AUDIODOC_URL, "process-document"),
            form,
            timeout,
            headers,
        )

    except TimeoutError as error:
        msg = "Document processing timed out"
        raise DocumentTimeoutError(msg) from error

    except aiohttp.ClientError as error:
        msg = f"Document Engine connection error: {error}"
        raise DocumentUnavailableError(msg) from error

    result = validate_document_response(raw_result)

    logger.info(
        "Document processed: filename=%s, format=%s, characters=%s",
        safe_filename,
        result["format"],
        result["characters"],
    )
    return result
