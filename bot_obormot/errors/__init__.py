# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Public exceptions raised by bot services."""

from bot_obormot.errors.audiodoc import (
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
    WhisperAPIError,
    WhisperEmptyAudioError,
    WhisperError,
    WhisperTimeoutError,
    WhisperUnavailableError,
)
from bot_obormot.errors.base import (
    AppError,
    BotServiceError,
    DatabaseError,
    InputTooLongError,
    MediaError,
    ValidationError,
)
from bot_obormot.errors.documents import (
    DocumentAPIError,
    DocumentError,
    DocumentTimeoutError,
    DocumentTooLongError,
    DocumentUnavailableError,
)
from bot_obormot.errors.llm import (
    LLMAPIError,
    LLMError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from bot_obormot.errors.telegram import TelegramError, TelegramFileTooBigError

__all__ = [
    "AppError",
    "AudiodocAPIError",
    "AudiodocEmptyAudioError",
    "AudiodocError",
    "AudiodocTimeoutError",
    "AudiodocUnavailableError",
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
