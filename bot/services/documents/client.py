import asyncio
import json
import logging
from pathlib import Path

import aiohttp

from bot.config import config
from bot.errors import (
    DocumentUnavailableError,
    DocumentTimeoutError,
    DocumentAPIError,
)
from bot.services.documents.response import validate_document_response
from bot.services.http_limits import (
    MAX_ERROR_BODY_BYTES,
    MAX_SERVICE_RESPONSE_BYTES,
    read_limited_body,
)
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)


async def process_document(
    document_data: bytes,
    filename: str,
) -> dict:
    """Отправляет документ в Document Engine и возвращает результат."""

    if not config.DOCUMENT_API_URL:
        raise DocumentUnavailableError("DOCUMENT_API_URL is not configured")

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

    timeout = aiohttp.ClientTimeout(total=config.DOCUMENT_TIMEOUT)
    headers = (
        {"Authorization": f"Bearer {config.DOCUMENT_API_KEY}"}
        if config.DOCUMENT_API_KEY
        else {}
    )

    try:
        logger.info(
            "Sending document: filename=%s, size=%s",
            safe_filename,
            len(document_data),
        )

        async with aiohttp.ClientSession(
            timeout=timeout,
            headers=headers,
        ) as session:
            async with session.post(
                config.DOCUMENT_API_URL,
                data=form,
            ) as response:
                if response.status != 200:
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

        return result

    except asyncio.TimeoutError as error:
        raise DocumentTimeoutError("Document processing timed out") from error

    except aiohttp.ClientError as error:
        raise DocumentUnavailableError(
            f"Document Engine connection error: {error}"
        ) from error
