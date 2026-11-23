# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Conversion of roleplay markup into Telegram HTML."""

import html

_BLOCKQUOTE_TAG = "blockquote"


def _render_segment(text: str) -> str:
    """Convert roleplay markup to safe Telegram HTML.

    *text*   -> italic
    **text** -> bold
    ~text~   -> thought block

    Unclosed markers are kept as plain text.
    """
    markers = {
        "**": "b",
        "*": "i",
        "~": _BLOCKQUOTE_TAG,
    }

    result = []
    i = 0

    while i < len(text):
        marker = None

        # Check double asterisks before single asterisks.
        for candidate in ("**", "*", "~"):
            if text.startswith(candidate, i):
                marker = candidate
                break

        if marker is None:
            # Collect plain text up to the next marker.
            next_positions = [
                pos for symbol in markers if (pos := text.find(symbol, i)) != -1
            ]

            next_pos = min(next_positions) if next_positions else len(text)

            result.append(html.escape(text[i:next_pos], quote=False))
            i = next_pos
            continue

        closing = text.find(marker, i + len(marker))

        if closing in {-1, i + len(marker)}:
            # Display an unclosed or empty marker literally.
            result.append(html.escape(marker, quote=False))
            i += len(marker)
            continue

        tag = markers[marker]
        inner = text[i + len(marker) : closing]

        formatted_inner = _render_segment(inner)

        if tag == _BLOCKQUOTE_TAG:
            result.append(f"\n<blockquote><i>{formatted_inner}</i></blockquote>\n")
        else:
            result.append(f"<{tag}>{formatted_inner}</{tag}>")

        i = closing + len(marker)

    return "".join(result)


def format_roleplay(text: str) -> str:
    """Format a character response as Telegram HTML."""
    if not text:
        return ""

    return _render_segment(text.strip())
