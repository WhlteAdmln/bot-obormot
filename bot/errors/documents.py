# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while processing documents."""

from typing import ClassVar

from bot.errors.base import AppError


class DocumentError(AppError):
    """Ошибка обработки документов."""

    code: ClassVar[str] = "document_error"
    public_message: ClassVar[str] = "Document processing failed"


class DocumentUnavailableError(DocumentError):
    """Document Engine недоступен."""

    code: ClassVar[str] = "document_unavailable"
    public_message: ClassVar[str] = "Document Engine is unavailable"


class DocumentTimeoutError(DocumentError):
    """Истекло время ожидания Document Engine."""

    code: ClassVar[str] = "document_timeout"
    public_message: ClassVar[str] = "Document Engine timed out"


class DocumentAPIError(DocumentError):
    """Document Engine вернул ошибку API."""

    code: ClassVar[str] = "document_api_error"
    public_message: ClassVar[str] = "Document Engine returned an error"

    def __init__(self, status: int, detail: str = "") -> None:
        """Stores the HTTP status and the error detail from the response."""
        self.status = status
        self.detail = detail
        super().__init__(f"Document Engine HTTP {status}: {detail}")


class DocumentTooLongError(DocumentError):
    """Извлечённый текст превышает допустимую длину."""

    code: ClassVar[str] = "document_too_long"
    public_message: ClassVar[str] = "Document text is too long"
