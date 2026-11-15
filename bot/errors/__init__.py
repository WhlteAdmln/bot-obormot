# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

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
    "DatabaseError",
    "DocumentAPIError",
    "DocumentError",
    "DocumentTimeoutError",
    "DocumentTooLongError",
    "DocumentUnavailableError",
    "InputTooLongError",
    "LLMAPIError",
    "LLMError",
    "LLMTimeoutError",
    "LLMUnavailableError",
    "MediaError",
    "TelegramError",
    "TelegramFileTooBigError",
    "ValidationError",
    "WhisperAPIError",
    "WhisperEmptyAudioError",
    "WhisperError",
    "WhisperTimeoutError",
    "WhisperUnavailableError",
]
