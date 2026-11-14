# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Форматирование сообщений для Telegram."""

from bot.services.chat.formatting.roleplay import format_roleplay
from bot.services.chat.formatting.splitter import split_formatted_message

__all__ = ["format_roleplay", "split_formatted_message"]
