# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Пользовательские сообщения для ошибок обработки чата."""

from bot.services.validation import MAX_INPUT_TEXT_LENGTH


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
