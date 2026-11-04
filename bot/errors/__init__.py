"""Публичные исключения сервисов бота."""

from bot.errors.base import (
    BotServiceError,
    DatabaseError,
    InputTooLongError,
    MediaError,
    ValidationError,
)
from bot.errors.documents import (
    DocumentAPIError,
    DocumentError,
    DocumentTimeoutError,
    DocumentTooLongError,
    DocumentUnavailableError,
)
from bot.errors.llm import (
    LLMAPIError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from bot.errors.telegram import TelegramError, TelegramFileTooBigError
from bot.errors.whisper import (
    WhisperAPIError,
    WhisperEmptyAudioError,
    WhisperError,
    WhisperTimeoutError,
    WhisperUnavailableError,
)

__all__ = [
    "BotServiceError",
    "ValidationError",
    "InputTooLongError",
    "LLMError",
    "LLMUnavailableError",
    "LLMTimeoutError",
    "LLMAPIError",
    "WhisperError",
    "WhisperEmptyAudioError",
    "WhisperUnavailableError",
    "WhisperTimeoutError",
    "WhisperAPIError",
    "DatabaseError",
    "MediaError",
    "TelegramError",
    "TelegramFileTooBigError",
    "DocumentError",
    "DocumentUnavailableError",
    "DocumentTimeoutError",
    "DocumentAPIError",
    "DocumentTooLongError",
]
