import asyncio
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

logger = logging.getLogger(__name__)


async def process_document(
    document_data: bytes,
    filename: str,
) -> dict:
    """Отправляет документ в Document Engine и возвращает результат."""

    if not config.DOCUMENT_API_URL:
        raise DocumentUnavailableError("DOCUMENT_API_URL is not configured")

    filename = Path(filename or "document").name

    form = aiohttp.FormData()
    form.add_field(
        "file",
        document_data,
        filename=filename,
        content_type="application/octet-stream",
    )

    timeout = aiohttp.ClientTimeout(total=config.DOCUMENT_TIMEOUT)

    try:
        logger.info(
            "Sending document: filename=%s, size=%s",
            filename,
            len(document_data),
        )

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                config.DOCUMENT_API_URL,
                data=form,
            ) as response:
                if response.status != 200:
                    detail = await response.text()

                    raise DocumentAPIError(
                        response.status,
                        detail[:1000],
                    )

                result = await response.json()

        result = validate_document_response(result)

        logger.info(
            "Document processed: filename=%s, format=%s, characters=%s",
            filename,
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
