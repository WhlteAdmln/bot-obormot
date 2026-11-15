# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while processing documents."""

from bot.errors.base import BotServiceError


class DocumentError(BotServiceError):
    """Ошибка обработки документов."""


class DocumentUnavailableError(DocumentError):
    """Document Engine недоступен."""


class DocumentTimeoutError(DocumentError):
    """Истекло время ожидания Document Engine."""


class DocumentAPIError(DocumentError):
    """Document Engine вернул ошибку API."""

    def __init__(self, status: int, detail: str = "") -> None:
        """Stores the HTTP status and the error detail from the response."""
        self.status = status
        self.detail = detail
        super().__init__(f"Document Engine HTTP {status}: {detail}")


class DocumentTooLongError(DocumentError):
    """Извлечённый текст превышает допустимую длину."""
