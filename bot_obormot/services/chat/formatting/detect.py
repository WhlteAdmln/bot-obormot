# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Automatic detection of the formatting used in an LLM response."""

import re
from typing import Literal

from bot_obormot.services.chat.formatting.tg_html import (
    has_supported_tags,
    is_balanced,
    mask_preformatted,
)

ResponseFormat = Literal["markdown", "html", "plain"]

_FENCED_CODE = re.compile(
    r"^[ ]{0,3}(`{3,}|~{3,})[^\n]*\n.*?(?:^[ ]{0,3}\1[`~]*[ \t]*$|\Z)",
    re.DOTALL | re.MULTILINE,
)
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.DOTALL)

_MARKDOWN_PATTERNS = tuple(
    re.compile(pattern, re.MULTILINE)
    for pattern in (
        r"^[ ]{0,3}#{1,6}[ \t]+\S",
        r"^[ ]{0,3}>[ \t]?\S",
        r"^[ \t]*(?:[-*+]|\d{1,9}[.)])[ \t]+\S",
        r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$",
        r"^[ \t]*\|.+\|[ \t]*$",
        r"(?<![\w*])\*\*(?=\S)[^\n]*?(?<=\S)\*\*(?![\w*])",
        r"(?<![\w*])\*(?=[^\s*])[^*\n]*(?<=[^\s*])\*(?![\w*])",
        r"(?<![\w_])__(?=\S)[^\n]*?(?<=\S)__(?![\w_])",
        r"(?<![\w_])_(?=[^\s_])[^_\n]*(?<=[^\s_])_(?![\w_])",
        r"~~(?=\S)[^\n]*?(?<=\S)~~",
        r"\[[^\]\n]+\]\((?:https?://|tg://|mailto:)[^)\s]+\)",
    )
)


def _has_markdown_syntax(text: str) -> bool:
    return any(pattern.search(text) for pattern in _MARKDOWN_PATTERNS)


def detect_format(text: str) -> ResponseFormat:
    """Detect whether the text is Markdown, Telegram HTML or plain text.

    Code is ignored when looking for foreign markup. When both Markdown and
    HTML markers are present, or HTML tags are broken, the result is
    ``plain`` so that the text is delivered without ``parse_mode``.
    """
    has_markdown = False

    without_fences, fence_count = _FENCED_CODE.subn("", text)
    has_markdown = fence_count > 0

    html_masked = mask_preformatted(without_fences)
    without_code, code_count = _INLINE_CODE.subn("", html_masked)
    has_markdown = has_markdown or code_count > 0
    has_markdown = has_markdown or _has_markdown_syntax(without_code)

    has_html = has_supported_tags(without_code)

    if has_html and has_markdown:
        return "plain"

    if has_html:
        return "html" if is_balanced(without_code) else "plain"

    return "markdown" if has_markdown else "plain"


__all__ = ["ResponseFormat", "detect_format"]
