# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Base exception types shared by all bot services."""

from typing import ClassVar


class AppError(Exception):
    """Base class for all application errors of the bot.

    Every concrete subclass declares a unique machine-readable ``code`` and a
    short English ``public_message`` that is safe to show outside the process
    (it never contains internal details such as URLs, HTTP bodies or secrets).
    The text for the end user is chosen by the outer layer from ``code``; for
    the chat it lives only in ``bot.services.chat.errors.texts``. The string
    form of an exception carries the internal detail and is meant for logs.
    """

    code: ClassVar[str] = "app_error"
    public_message: ClassVar[str] = "Internal application error"


class ValidationError(AppError):
    """Ошибка проверки входных данных."""

    code: ClassVar[str] = "validation_error"
    public_message: ClassVar[str] = "Invalid input"


class InputTooLongError(ValidationError):
    """Пользовательское сообщение превышает допустимую длину."""

    code: ClassVar[str] = "input_too_long"
    public_message: ClassVar[str] = "Input is too long"


class DatabaseError(AppError):
    """Ошибка SQLite или операций с базой данных."""

    code: ClassVar[str] = "database_error"
    public_message: ClassVar[str] = "Database operation failed"


class MediaError(AppError):
    """Ошибка обработки или хранения медиафайлов."""

    code: ClassVar[str] = "media_error"
    public_message: ClassVar[str] = "Media processing failed"


# Deprecated alias kept for one release. Use ``AppError`` instead.
BotServiceError = AppError
