# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Splitting of Telegram HTML messages that exceed the length limit."""

import html
import re

from bot_obormot.common.text import utf16_length
from bot_obormot.services.chat.formatting.tg_html import SUPPORTED_TAGS

_utf16_length = utf16_length


class _FormattedMessageSplitter:
    def __init__(self, text: str, max_length: int) -> None:
        self.text = text
        self.max_length = max_length
        self.token_pattern = re.compile(
            r"<(/?)(" + "|".join(SUPPORTED_TAGS) + r")(?:\s[^<>]*)?>"
            r"|&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);"
            r"|[^<&]+"
            r"|[<&]",
            re.IGNORECASE,
        )
        self.chunks: list[str] = []
        self.current: list[str] = []
        # Pairs of (tag name, original opening token) so attributes survive.
        self.open_tags: list[tuple[str, str]] = []
        self.visible_length = 0

    def split(self) -> list[str]:
        """Split the text into chunks, closing and reopening tags at each cut."""
        for match in self.token_pattern.finditer(self.text):
            token = match.group(0)

            # A lone "<" is plain text, only a complete supported tag is markup.
            if match.group(2) is not None:
                self._append_tag(token, match)
                continue

            if token.startswith("&") and token.endswith(";"):
                self._append_entity(token)
                continue

            self._append_text(token)

        if self.current:
            chunk = "".join(self.current) + self._close_tags()
            if chunk:
                self.chunks.append(chunk)

        return self.chunks

    def _close_tags(self) -> str:
        return "".join(f"</{name}>" for name, _ in reversed(self.open_tags))

    def _start_next_chunk(self) -> None:
        self.current = [token for _, token in self.open_tags]
        self.visible_length = 0

    def _flush(self) -> None:
        if not self.current:
            return

        chunk = "".join(self.current) + self._close_tags()
        if chunk:
            self.chunks.append(chunk)

        self._start_next_chunk()

    def _append_tag(self, token: str, match: re.Match[str]) -> None:
        self.current.append(token)
        closing = match.group(1)
        tag = match.group(2).lower()

        if closing:
            names = [name for name, _ in self.open_tags]
            if tag in names:
                # Remove the matching open tag.
                index = len(names) - 1 - names[::-1].index(tag)
                self.open_tags.pop(index)
        else:
            self.open_tags.append((tag, token))

    def _append_entity(self, token: str) -> None:
        decoded = html.unescape(token)
        token_length = _utf16_length(decoded)

        if self.visible_length + token_length > self.max_length:
            self._flush()

        self.current.append(token)
        self.visible_length += token_length

    def _append_text(self, token: str) -> None:
        for char in token:
            char_length = _utf16_length(char)

            if self.visible_length + char_length > self.max_length:
                self._flush()

            self.current.append(char)
            self.visible_length += char_length


def split_formatted_message(
    text: str,
    max_length: int = 3900,
) -> list[str]:
    """Splits Telegram HTML into parts without breaking tags or entities.

    Open tags are closed at the end of each part and reopened at the start
    of the next part.
    """
    if not text:
        return []

    if max_length < 1:
        msg = "max_length must be greater than zero."
        raise ValueError(msg)

    return _FormattedMessageSplitter(text, max_length).split()
