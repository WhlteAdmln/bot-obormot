# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Application error subclasses for error-text tests."""

from bot_obormot.errors import AppError, LLMTimeoutError


class UnmappedError(AppError):
    """An application error whose code has no user text."""

    code = "not_in_the_table"


class CustomTimeoutError(LLMTimeoutError):
    """A timeout subclass that declares no code of its own."""
