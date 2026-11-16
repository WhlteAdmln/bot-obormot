# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while talking to Telegram."""

from typing import ClassVar

from bot.errors.base import AppError


class TelegramError(AppError):
    """Ошибка взаимодействия с Telegram."""

    code: ClassVar[str] = "telegram_error"
    public_message: ClassVar[str] = "Telegram operation failed"


class TelegramFileTooBigError(TelegramError):
    """Telegram не позволяет скачать файл из-за его размера."""

    code: ClassVar[str] = "telegram_file_too_big"
    public_message: ClassVar[str] = "Telegram file is too big to download"
