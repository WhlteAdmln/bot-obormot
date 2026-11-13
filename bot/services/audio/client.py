# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Client for the Whisper speech-to-text API."""

import json
import logging
from http import HTTPStatus

import aiohttp

from bot.config import config
from bot.errors import (
    WhisperAPIError,
    WhisperEmptyAudioError,
    WhisperTimeoutError,
    WhisperUnavailableError,
)
from bot.services.http_limits import (
    MAX_ERROR_BODY_BYTES,
    MAX_SERVICE_RESPONSE_BYTES,
    read_limited_body,
)
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)


def _extract_text(result: object) -> str:
    """Returns the transcribed text from the Whisper response or raises."""
    if not isinstance(result, dict):
        msg = "Whisper returned an unexpected response"
        raise WhisperAPIError(msg)

    text = str(result.get("text", "")).strip()

    if not text:
        msg = "No speech detected in audio"
        raise WhisperEmptyAudioError(msg)

    return text


async def transcribe_audio(
    audio_data: bytes,
    filename: str = "audio.ogg",
) -> str:
    """Отправляет аудио в Whisper и возвращает распознанный текст."""
    if not config.WHISPER_API_URL:
        msg = "WHISPER_API_URL is not configured"
        raise WhisperUnavailableError(msg)

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

    timeout = aiohttp.ClientTimeout(total=config.WHISPER_TIMEOUT)
    headers = (
        {"Authorization": f"Bearer {config.WHISPER_API_KEY}"}
        if config.WHISPER_API_KEY
        else {}
    )

    try:
        logger.info(
            "Sending audio to Whisper: filename=%s, size=%s",
            safe_filename,
            len(audio_data),
        )

        async with (
            aiohttp.ClientSession(
                timeout=timeout,
                headers=headers,
            ) as session,
            session.post(
                config.WHISPER_API_URL,
                data=form,
            ) as response,
        ):
            if response.status != HTTPStatus.OK:
                body = await read_limited_body(response, MAX_ERROR_BODY_BYTES)
                detail = (body or b"").decode("utf-8", errors="replace")
                msg = f"Whisper HTTP {response.status}: {detail[:1000]}"
                raise WhisperAPIError(msg)

            body = await read_limited_body(response, MAX_SERVICE_RESPONSE_BYTES)

            if body is None:
                msg = "Whisper response is too large"
                raise WhisperAPIError(msg)

            try:
                result = json.loads(body)
            except ValueError as error:
                msg = "Whisper returned invalid JSON"
                raise WhisperAPIError(msg) from error

        text = _extract_text(result)

        logger.info("Whisper transcription received: %d chars", len(text))

    except TimeoutError as error:
        msg = "Whisper request timed out"
        raise WhisperTimeoutError(msg) from error

    except aiohttp.ClientError as error:
        msg = f"Whisper connection error: {error}"
        raise WhisperUnavailableError(msg) from error

    else:
        return text
