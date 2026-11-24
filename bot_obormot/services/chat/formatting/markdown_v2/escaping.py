# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Escaping of text, code and URLs for Telegram MarkdownV2."""

_RESERVED = frozenset("_*[]()~`>#+-=|{}.!\\")


def escape_text(text: str) -> str:
    """Escape characters reserved by MarkdownV2 outside of code."""
    return "".join(f"\\{c}" if c in _RESERVED else c for c in text)


def escape_code(text: str) -> str:
    """Escape the characters MarkdownV2 reserves inside code."""
    return text.replace("\\", "\\\\").replace("`", "\\`")


def escape_url(text: str) -> str:
    """Escape the characters MarkdownV2 reserves inside a link URL."""
    return text.replace("\\", "\\\\").replace(")", "\\)")


__all__ = ["escape_code", "escape_text", "escape_url"]
