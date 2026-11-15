# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while talking to Telegram."""

from bot.errors.base import BotServiceError


class TelegramError(BotServiceError):
    """Ошибка взаимодействия с Telegram."""


class TelegramFileTooBigError(TelegramError):
    """Telegram не позволяет скачать файл из-за его размера."""
