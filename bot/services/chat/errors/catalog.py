"""Упорядоченный каталог правил обработки ошибок чата.

Порядок элементов повторяет исходную последовательность elif, включая
специализированные подклассы перед базовыми типами.
"""

import logging
from dataclasses import dataclass
from typing import Callable

from bot.errors import (
    InputTooLongError,
    WhisperError,
    WhisperUnavailableError,
    WhisperTimeoutError,
    WhisperAPIError,
    WhisperEmptyAudioError,
    TelegramError,
    MediaError,
    TelegramFileTooBigError,
    LLMUnavailableError,
    LLMTimeoutError,
    LLMAPIError,
    DatabaseError,
    DocumentAPIError,
    DocumentTimeoutError,
    DocumentUnavailableError,
    DocumentTooLongError,
)
from bot.services.chat.errors import texts


@dataclass(frozen=True)
class ChatErrorRule:
    error_type: type[Exception]
    user_message: str | Callable[[Exception], str]
    log_method: str | None = None
    log_template: str | None = None
    log_fields: tuple[str, ...] = ()
    traceback: bool = False


CHAT_ERROR_RULES: tuple[ChatErrorRule, ...] = (
    ChatErrorRule(InputTooLongError, texts.INPUT_TOO_LONG),
    ChatErrorRule(
        TelegramFileTooBigError,
        texts.TELEGRAM_FILE_TOO_BIG,
        "warning",
        "Telegram file is too big to download, user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(DocumentTooLongError, texts.DOCUMENT_TOO_LONG),
    ChatErrorRule(
        DocumentTimeoutError,
        texts.DOCUMENT_TIMEOUT,
        "warning",
        "Document processing timed out for user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        DocumentUnavailableError,
        texts.DOCUMENT_UNAVAILABLE,
        "error",
        "Document Engine unavailable for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        DocumentAPIError,
        texts.DOCUMENT_API,
        "error",
        "Document Engine API error for user_id=%s: HTTP %s, %s",
        ("user_id", "status", "detail"),
    ),
    ChatErrorRule(
        WhisperEmptyAudioError,
        texts.WHISPER_EMPTY_AUDIO,
        "info",
        "No speech detected in audio from user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        WhisperTimeoutError,
        texts.WHISPER_TIMEOUT,
        "warning",
        "Whisper request timed out for user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        WhisperUnavailableError,
        texts.WHISPER_UNAVAILABLE,
        "error",
        "Whisper is unavailable for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        WhisperAPIError,
        texts.WHISPER_API,
        "error",
        "Whisper API error for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        WhisperError,
        texts.WHISPER_ERROR,
        "error",
        "Whisper error for user_id=%s",
        ("user_id",),
        traceback=True,
    ),
    ChatErrorRule(
        MediaError,
        lambda error: texts.MEDIA_ERROR_PREFIX + str(error),
        "warning",
        "Media processing failed for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        TelegramError,
        texts.TELEGRAM_ERROR,
        "error",
        "Telegram operation failed for user_id=%s",
        ("user_id",),
        traceback=True,
    ),
    ChatErrorRule(
        LLMTimeoutError,
        texts.LLM_TIMEOUT,
        "warning",
        "LLM request timed out for user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        LLMUnavailableError,
        texts.LLM_UNAVAILABLE,
        "error",
        "LLM is unavailable for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        LLMAPIError,
        texts.LLM_API,
        "error",
        "LLM API error for user_id=%s: HTTP %s, %s",
        ("user_id", "status", "detail"),
    ),
    ChatErrorRule(
        DatabaseError,
        texts.DATABASE_ERROR,
        "error",
        "Database operation failed for user_id=%s",
        ("user_id",),
        traceback=True,
    ),
)

__all__ = ["ChatErrorRule", "CHAT_ERROR_RULES"]
