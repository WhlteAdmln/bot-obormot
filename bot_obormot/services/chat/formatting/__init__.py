# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Telegram message formatting."""

from bot_obormot.services.chat.formatting.detect import detect_format
from bot_obormot.services.chat.formatting.markdown_v2 import to_markdown_v2
from bot_obormot.services.chat.formatting.prepare import (
    FormattedChunk,
    prepare_response,
)
from bot_obormot.services.chat.formatting.splitter import split_formatted_message
from bot_obormot.services.chat.formatting.text_splitter import (
    split_markdown_message,
    split_plain_message,
)
from bot_obormot.services.chat.formatting.tg_html import sanitize_html

__all__ = [
    "FormattedChunk",
    "detect_format",
    "prepare_response",
    "sanitize_html",
    "split_formatted_message",
    "split_markdown_message",
    "split_plain_message",
    "to_markdown_v2",
]
