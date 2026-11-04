import asyncio
import logging

import aiohttp

from bot.config import config
from bot.errors import (
    WhisperUnavailableError,
    WhisperTimeoutError,
    WhisperAPIError,
    WhisperEmptyAudioError,
)

logger = logging.getLogger(__name__)


async def transcribe_audio(
    audio_data: bytes,
    filename: str = "audio.ogg",
) -> str:
    """Отправляет аудио в Whisper и возвращает распознанный текст."""

    if not config.WHISPER_API_URL:
        raise WhisperUnavailableError("WHISPER_API_URL is not configured")

    form = aiohttp.FormData()
    form.add_field(
        "file",
        audio_data,
        filename=filename,
        content_type="application/octet-stream",
    )

    timeout = aiohttp.ClientTimeout(total=config.WHISPER_TIMEOUT)

    try:
        logger.info(
            "Sending audio to Whisper: url=%s, filename=%s, size=%s",
            config.WHISPER_API_URL,
            filename,
            len(audio_data),
        )

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                config.WHISPER_API_URL,
                data=form,
            ) as response:
                if response.status != 200:
                    detail = await response.text()
                    raise WhisperAPIError(
                        f"Whisper HTTP {response.status}: {detail[:1000]}"
                    )

                result = await response.json()

        text = result.get("text", "").strip()

        if not text:
            raise WhisperEmptyAudioError("No speech detected in audio")

        logger.info("Whisper transcription: %s", text)

        return text

    except asyncio.TimeoutError as error:
        raise WhisperTimeoutError("Whisper request timed out") from error

    except aiohttp.ClientError as error:
        raise WhisperUnavailableError(f"Whisper connection error: {error}") from error
