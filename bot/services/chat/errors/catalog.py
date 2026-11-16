# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Упорядоченный каталог правил обработки ошибок чата.

Порядок элементов повторяет исходную последовательность elif, включая
специализированные подклассы перед базовыми типами.
"""

from dataclasses import dataclass

from bot.errors import (
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
    DatabaseError,
    DocumentAPIError,
    DocumentTimeoutError,
    DocumentTooLongError,
    DocumentUnavailableError,
    InputTooLongError,
    LLMAPIError,
    LLMTimeoutError,
    LLMUnavailableError,
    MediaError,
    TelegramError,
    TelegramFileTooBigError,
)


@dataclass(frozen=True)
class ChatErrorRule:
    """Maps an error type to the log entry it produces.

    The user text is not stored here: it is chosen by the error ``code`` in
    ``bot.services.chat.errors.texts``.
    """

    error_type: type[Exception]
    log_method: str | None = None
    log_template: str | None = None
    log_fields: tuple[str, ...] = ()
    traceback: bool = False


CHAT_ERROR_RULES: tuple[ChatErrorRule, ...] = (
    ChatErrorRule(InputTooLongError),
    ChatErrorRule(
        TelegramFileTooBigError,
        "warning",
        "Telegram file is too big to download, user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(DocumentTooLongError),
    ChatErrorRule(
        DocumentTimeoutError,
        "warning",
        "Document processing timed out for user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        DocumentUnavailableError,
        "error",
        "Document Engine unavailable for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        DocumentAPIError,
        "error",
        "Document Engine API error for user_id=%s: HTTP %s, %s",
        ("user_id", "status", "detail"),
    ),
    ChatErrorRule(
        AudiodocEmptyAudioError,
        "info",
        "No speech detected in audio from user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        AudiodocTimeoutError,
        "warning",
        "Whisper request timed out for user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        AudiodocUnavailableError,
        "error",
        "Whisper is unavailable for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        AudiodocAPIError,
        "error",
        "Whisper API error for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        AudiodocError,
        "error",
        "Whisper error for user_id=%s",
        ("user_id",),
        traceback=True,
    ),
    ChatErrorRule(
        MediaError,
        "warning",
        "Media processing failed for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        TelegramError,
        "error",
        "Telegram operation failed for user_id=%s",
        ("user_id",),
        traceback=True,
    ),
    ChatErrorRule(
        LLMTimeoutError,
        "warning",
        "LLM request timed out for user_id=%s",
        ("user_id",),
    ),
    ChatErrorRule(
        LLMUnavailableError,
        "error",
        "LLM is unavailable for user_id=%s: %s",
        ("user_id", "error"),
    ),
    ChatErrorRule(
        LLMAPIError,
        "error",
        "LLM API error for user_id=%s: HTTP %s, %s",
        ("user_id", "status", "detail"),
    ),
    ChatErrorRule(
        DatabaseError,
        "error",
        "Database operation failed for user_id=%s",
        ("user_id",),
        traceback=True,
    ),
)

__all__ = [
    "CHAT_ERROR_RULES",
    "ChatErrorRule",
]
