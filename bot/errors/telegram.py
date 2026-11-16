# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while talking to Telegram."""

from typing import ClassVar

from bot.errors.base import AppError


class TelegramError(AppError):
    """An error occurred while interacting with Telegram."""

    code: ClassVar[str] = "telegram_error"
    public_message: ClassVar[str] = "Telegram operation failed"


class TelegramFileTooBigError(TelegramError):
    """Telegram does not allow downloading a file because of its size."""

    code: ClassVar[str] = "telegram_file_too_big"
    public_message: ClassVar[str] = "Telegram file is too big to download"
