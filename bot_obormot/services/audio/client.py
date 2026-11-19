# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Client for the audiodoc transcription API."""

import json
import logging
from http import HTTPStatus
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from bot_obormot.common.http_limits import (
    MAX_ERROR_BODY_BYTES,
    MAX_SERVICE_RESPONSE_BYTES,
    read_limited_body,
)
from bot_obormot.common.text import log_safe
from bot_obormot.errors import (
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
)
from bot_obormot.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def _endpoint_url(base_url: str, endpoint: str) -> str:
    parts = urlsplit(base_url)
    path = f"{parts.path.rstrip('/')}/{endpoint}"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _extract_text(result: object) -> str:
    """Returns the transcribed text from the audiodoc response or raises."""
    if not isinstance(result, dict):
        msg = "audiodoc returned an unexpected response"
        raise AudiodocAPIError(msg)

    text = str(result.get("text", "")).strip()

    if not text:
        msg = "No speech detected in audio"
        raise AudiodocEmptyAudioError(msg)

    return text


async def transcribe_audio(
    audio_data: bytes,
    filename: str = "audio.ogg",
    *,
    settings: Settings | None = None,
) -> str:
    """Send audio to audiodoc and return the transcribed text."""
    if settings is None:
        settings = get_settings()

    if not settings.AUDIODOC_URL:
        msg = "AUDIODOC_URL is not configured"
        raise AudiodocUnavailableError(msg)

    # The filename is also embedded in a multipart header. Normalize it before
    # handing it to aiohttp so CR/LF and other control characters cannot break
    # the header (or be used for header injection).
    safe_filename = log_safe(filename or "audio.ogg", limit=255)

    form = aiohttp.FormData()
    form.add_field(
        "file",
        audio_data,
        filename=safe_filename,
        content_type="application/octet-stream",
    )

    timeout = aiohttp.ClientTimeout(total=settings.AUDIODOC_AUDIO_TIMEOUT)
    headers = (
        {"Authorization": f"Bearer {settings.AUDIODOC_AUDIO_KEY}"}
        if settings.AUDIODOC_AUDIO_KEY
        else {}
    )

    try:
        logger.info(
            "Sending audio to audiodoc: filename=%s, size=%s",
            safe_filename,
            len(audio_data),
        )

        async with (
            aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session,
            session.post(
                _endpoint_url(settings.AUDIODOC_URL, "transcribe"),
                data=form,
            ) as response,
        ):
            if response.status != HTTPStatus.OK:
                body = await read_limited_body(response, MAX_ERROR_BODY_BYTES)
                detail = (body or b"").decode("utf-8", errors="replace")
                msg = f"audiodoc HTTP {response.status}: {detail[:1000]}"
                raise AudiodocAPIError(msg)

            body = await read_limited_body(response, MAX_SERVICE_RESPONSE_BYTES)

            if body is None:
                msg = "audiodoc response is too large"
                raise AudiodocAPIError(msg)

            try:
                result = json.loads(body)
            except ValueError as error:
                msg = "audiodoc returned invalid JSON"
                raise AudiodocAPIError(msg) from error

        text = _extract_text(result)

        logger.info("audiodoc transcription received: %d chars", len(text))

    except TimeoutError as error:
        msg = "audiodoc request timed out"
        raise AudiodocTimeoutError(msg) from error

    except aiohttp.ClientError as error:
        msg = f"audiodoc connection error: {error}"
        raise AudiodocUnavailableError(msg) from error

    else:
        return text
