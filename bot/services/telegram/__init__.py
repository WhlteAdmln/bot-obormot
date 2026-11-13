# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Интеграция с Telegram API."""

from bot.services.telegram.chat_action import keep_typing
from bot.services.telegram.downloader import download_telegram_file

__all__ = ["download_telegram_file", "keep_typing"]
