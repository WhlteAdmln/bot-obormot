import json
import logging

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


async def transcribe_audio(
    audio_data: bytes,
    filename: str = "audio.ogg",
) -> str:
    """Отправляет аудио в Whisper и возвращает распознанный текст."""

    if not config.WHISPER_API_URL:
        raise WhisperUnavailableError("WHISPER_API_URL is not configured")

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
            if response.status != 200:
                body = await read_limited_body(response, MAX_ERROR_BODY_BYTES)
                detail = (body or b"").decode("utf-8", errors="replace")
                raise WhisperAPIError(
                    f"Whisper HTTP {response.status}: {detail[:1000]}"
                )

            body = await read_limited_body(response, MAX_SERVICE_RESPONSE_BYTES)

            if body is None:
                raise WhisperAPIError("Whisper response is too large")

            try:
                result = json.loads(body)
            except ValueError as error:
                raise WhisperAPIError("Whisper returned invalid JSON") from error

        if not isinstance(result, dict):
            raise WhisperAPIError("Whisper returned an unexpected response")

        text = str(result.get("text", "")).strip()

        if not text:
            raise WhisperEmptyAudioError("No speech detected in audio")

        logger.info("Whisper transcription received: %d chars", len(text))

        return text

    except TimeoutError as error:
        raise WhisperTimeoutError("Whisper request timed out") from error

    except aiohttp.ClientError as error:
        raise WhisperUnavailableError(f"Whisper connection error: {error}") from error
