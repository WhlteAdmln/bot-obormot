# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while talking to the LLM server."""

from typing import ClassVar

from bot.errors.base import AppError


class LLMError(AppError):
    """An error occurred while interacting with the LLM."""

    code: ClassVar[str] = "llm_error"
    public_message: ClassVar[str] = "LLM request failed"


class LLMUnavailableError(LLMError):
    """The LLM is unavailable or the connection could not be established."""

    code: ClassVar[str] = "llm_unavailable"
    public_message: ClassVar[str] = "LLM server is unavailable"


class LLMTimeoutError(LLMError):
    """Timed out while waiting for an LLM response."""

    code: ClassVar[str] = "llm_timeout"
    public_message: ClassVar[str] = "LLM server timed out"


class LLMAPIError(LLMError):
    """The LLM returned an API error."""

    code: ClassVar[str] = "llm_api_error"
    public_message: ClassVar[str] = "LLM server returned an error"

    def __init__(self, status: int, detail: str = "") -> None:
        """Stores the HTTP status and the error detail from the response."""
        self.status = status
        self.detail = detail
        super().__init__(f"LLM API HTTP {status}: {detail}")
