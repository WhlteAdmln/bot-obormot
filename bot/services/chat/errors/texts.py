# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Пользовательские сообщения для ошибок обработки чата."""

from collections.abc import Callable

from bot.common.validation import MAX_INPUT_TEXT_LENGTH
from bot.errors import AppError


def _formatted_input_limit() -> str:
    """Return the configured character limit with a readable thousands separator."""
    return f"{MAX_INPUT_TEXT_LENGTH:,}".replace(",", " ")


def input_too_long(_error: Exception) -> str:
    """Returns the message for an input that exceeds the length limit."""
    return (
        "📄 Сообщение слишком длинное. Максимальный объём — "
        f"{_formatted_input_limit()} символов."
    )


TELEGRAM_FILE_TOO_BIG = (
    "📦 Файл слишком большой для скачивания через Telegram. "
    "Попробуй отправить файл меньшего размера."
)


def document_too_long(_error: Exception) -> str:
    """Returns the message for a document with too much text."""
    return (
        "📄 В документе слишком много текста. "
        "Максимальный объём для обработки сейчас — "
        f"{_formatted_input_limit()} символов."
    )


DOCUMENT_TIMEOUT = (
    "⏳ Обработка документа заняла слишком много времени. Попробуй ещё раз позже."
)
DOCUMENT_UNAVAILABLE = "🔌 Не удалось связаться с сервисом обработки документов."
DOCUMENT_API = (
    "⚠️ Не удалось обработать документ. Проверь его формат или попробуй другой файл."
)
WHISPER_EMPTY_AUDIO = (
    "🎤 Не удалось распознать речь. Попробуй записать голосовое сообщение ещё раз."
)
WHISPER_TIMEOUT = (
    "⏳ Сервис распознавания аудио не успел ответить. "
    "Попробуй отправить голосовое сообщение ещё раз."
)
WHISPER_UNAVAILABLE = "🔌 Не удалось связаться с сервисом распознавания аудио."
WHISPER_API = "⚠️ Сервис распознавания аудио вернул ошибку. Попробуй немного позже."
WHISPER_ERROR = "🎤 Не удалось обработать аудио. Попробуй отправить его ещё раз."
MEDIA_ERROR_PREFIX = "⚠️ "
TELEGRAM_ERROR = (
    "📡 Не удалось получить файл от Telegram. Попробуй отправить его ещё раз."
)
LLM_TIMEOUT = "⏳ Модель слишком долго отвечает. Попробуй отправить сообщение ещё раз."
LLM_UNAVAILABLE = (
    "🔌 Не удалось связаться с языковой моделью. Проверь доступность AI-сервера."
)
LLM_API = "⚠️ Языковая модель вернула ошибку. Попробуй немного позже."
DATABASE_ERROR = (
    "💾 Возникла ошибка при работе с историей диалога. "
    "Попробуй отправить сообщение ещё раз."
)
UNEXPECTED_ERROR = "❌ Произошла непредвиденная ошибка. Попробуй ещё раз."


def media_error(error: Exception) -> str:
    """Returns the message for a media error, which carries its own user text."""
    return MEDIA_ERROR_PREFIX + str(error)


# The only place that maps ``AppError.code`` to the text shown to the user.
# Every code declared by a subclass of ``AppError`` must have an entry here.
# Generic base codes share the unexpected-error text on purpose.
USER_TEXTS: dict[str, str | Callable[[Exception], str]] = {
    "app_error": UNEXPECTED_ERROR,
    "validation_error": UNEXPECTED_ERROR,
    "input_too_long": input_too_long,
    "database_error": DATABASE_ERROR,
    "media_error": media_error,
    "document_error": UNEXPECTED_ERROR,
    "document_unavailable": DOCUMENT_UNAVAILABLE,
    "document_timeout": DOCUMENT_TIMEOUT,
    "document_api_error": DOCUMENT_API,
    "document_too_long": document_too_long,
    "llm_error": UNEXPECTED_ERROR,
    "llm_unavailable": LLM_UNAVAILABLE,
    "llm_timeout": LLM_TIMEOUT,
    "llm_api_error": LLM_API,
    "telegram_error": TELEGRAM_ERROR,
    "telegram_file_too_big": TELEGRAM_FILE_TOO_BIG,
    "audiodoc_error": WHISPER_ERROR,
    "audiodoc_empty_audio": WHISPER_EMPTY_AUDIO,
    "audiodoc_unavailable": WHISPER_UNAVAILABLE,
    "audiodoc_timeout": WHISPER_TIMEOUT,
    "audiodoc_api_error": WHISPER_API,
}


def user_text(error: Exception) -> str:
    """Returns the user-facing text for an error, chosen by its ``code``.

    Errors that are not ``AppError`` or whose code has no entry get the
    unexpected-error text.
    """
    if not isinstance(error, AppError):
        return UNEXPECTED_ERROR
    entry = USER_TEXTS.get(error.code)
    if entry is None:
        return UNEXPECTED_ERROR
    return entry(error) if callable(entry) else entry
