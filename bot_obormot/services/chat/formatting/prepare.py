# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Prepare an LLM response for delivery to Telegram."""

from dataclasses import dataclass

from bot_obormot.services.chat.formatting.detect import detect_format
from bot_obormot.services.chat.formatting.markdown_v2 import to_markdown_v2
from bot_obormot.services.chat.formatting.splitter import split_formatted_message
from bot_obormot.services.chat.formatting.text_splitter import (
    split_markdown_message,
    split_plain_message,
)
from bot_obormot.services.chat.formatting.tg_html import sanitize_html

MARKDOWN_V2 = "MarkdownV2"
HTML = "HTML"


@dataclass(frozen=True, slots=True)
class FormattedChunk:
    """One Telegram message: formatted text and its unchanged source text."""

    text: str
    parse_mode: str | None
    plain_text: str


def _plain(part: str) -> FormattedChunk:
    return FormattedChunk(text=part, parse_mode=None, plain_text=part)


def _formatted(part: str, text: str, parse_mode: str) -> FormattedChunk:
    # An empty converted text would be rejected for a reason unrelated to
    # entities, so such parts are sent as they are.
    if not text.strip():
        return _plain(part)
    return FormattedChunk(text=text, parse_mode=parse_mode, plain_text=part)


def prepare_response(text: str, max_length: int = 3900) -> list[FormattedChunk]:
    """Detect the format, split the response and convert every part.

    The split is made on the original text, so ``plain_text`` of each chunk
    is the unchanged LLM output and can be used for the safe fallback.
    """
    response_format = detect_format(text)
    text = text.strip()

    if response_format == "html":
        parts = split_formatted_message(text, max_length=max_length)
        return [_formatted(p, sanitize_html(p), HTML) for p in parts if p.strip()]

    if response_format == "markdown":
        parts = split_markdown_message(text, max_length)
        return [_formatted(p, to_markdown_v2(p), MARKDOWN_V2) for p in parts]

    return [_plain(part) for part in split_plain_message(text, max_length)]


__all__ = [
    "HTML",
    "MARKDOWN_V2",
    "FormattedChunk",
    "prepare_response",
]
