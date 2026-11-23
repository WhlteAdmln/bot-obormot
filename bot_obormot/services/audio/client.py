# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Client for the audiodoc transcription API."""

import logging
from http import HTTPStatus

import aiohttp

from bot_obormot.common.text import log_safe
from bot_obormot.errors import (
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
)
from bot_obormot.services.audiodoc_http import (
    bearer_headers,
    endpoint_url,
    file_form,
    post_form,
    require_base_url,
)
from bot_obormot.settings import Settings

logger = logging.getLogger(__name__)


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


async def _post_audio(
    url: str,
    form: aiohttp.FormData,
    client_timeout: aiohttp.ClientTimeout,
    headers: dict[str, str],
) -> object:
    """Post the audio form and return the decoded JSON response."""
    response = await post_form(url, form, client_timeout, headers)
    if response.status != HTTPStatus.OK:
        msg = f"audiodoc HTTP {response.status}: {response.detail[:1000]}"
        raise AudiodocAPIError(msg)

    if response.body is None:
        msg = "audiodoc response is too large"
        raise AudiodocAPIError(msg)

    try:
        return response.json()
    except ValueError as error:
        msg = "audiodoc returned invalid JSON"
        raise AudiodocAPIError(msg) from error


async def transcribe_audio(
    audio_data: bytes,
    filename: str = "audio.ogg",
    *,
    settings: Settings | None = None,
) -> str:
    """Send audio to audiodoc and return the transcribed text."""
    settings = require_base_url(settings, AudiodocUnavailableError)

    # The filename is also embedded in a multipart header. Normalize it before
    # handing it to aiohttp so CR/LF and other control characters cannot break
    # the header (or be used for header injection).
    safe_filename = log_safe(filename or "audio.ogg", limit=255)

    form = file_form(audio_data, safe_filename)

    timeout = aiohttp.ClientTimeout(total=settings.AUDIODOC_AUDIO_TIMEOUT)
    headers = bearer_headers(settings.AUDIODOC_AUDIO_KEY)

    logger.info(
        "Sending audio to audiodoc: filename=%s, size=%s",
        safe_filename,
        len(audio_data),
    )

    try:
        result = await _post_audio(
            endpoint_url(settings.AUDIODOC_URL, "transcribe"),
            form,
            timeout,
            headers,
        )

    except TimeoutError as error:
        msg = "audiodoc request timed out"
        raise AudiodocTimeoutError(msg) from error

    except aiohttp.ClientError as error:
        msg = f"audiodoc connection error: {error}"
        raise AudiodocUnavailableError(msg) from error

    text = _extract_text(result)

    logger.info("audiodoc transcription received: %d chars", len(text))
    return text
