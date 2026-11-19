# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Telegram message formatting."""

from bot_obormot.services.chat.formatting.roleplay import format_roleplay
from bot_obormot.services.chat.formatting.splitter import split_formatted_message

__all__ = ["format_roleplay", "split_formatted_message"]
