# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Validation and sanitizing of the Telegram HTML subset."""

import html
import re
from collections.abc import Callable

# Tags supported by Telegram ``parse_mode=HTML``.
SUPPORTED_TAGS: tuple[str, ...] = (
    "tg-spoiler",
    "tg-emoji",
    "blockquote",
    "strong",
    "strike",
    "span",
    "pre",
    "code",
    "ins",
    "del",
    "em",
    "a",
    "b",
    "i",
    "u",
    "s",
)

TAG_PATTERN = re.compile(
    r"<(/?)(" + "|".join(SUPPORTED_TAGS) + r")(\s[^<>]*)?>",
    re.IGNORECASE,
)
_ANY_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(\s[^<>]*?)?\s*(/?)>")
_ATTRIBUTE = re.compile(
    r"([a-zA-Z][a-zA-Z0-9-]*)(?:\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>]+)))?"
)
_ENTITY = re.compile(r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")
_TELEGRAM_NAMED_ENTITIES = frozenset({"&lt;", "&gt;", "&amp;", "&quot;"})
_SAFE_URL = re.compile(r"^(?:https?://|tg://|mailto:)\S+$", re.IGNORECASE)
_LANGUAGE_CLASS = re.compile(r"^language-[A-Za-z0-9_+#.-]+$")
_DIGITS = re.compile(r"^[0-9]+$")
_PREFORMATTED = re.compile(
    r"<(pre|code)\b[^<>]*>.*?</\1\s*>",
    re.DOTALL | re.IGNORECASE,
)
_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)


def mask_preformatted(text: str) -> str:
    """Replace the content of ``<pre>``/``<code>`` with empty tags."""
    return _PREFORMATTED.sub(lambda m: f"<{m.group(1)}></{m.group(1)}>", text)


def is_balanced(text: str) -> bool:
    """Return True when every supported tag is properly opened and closed."""
    stack: list[str] = []

    for match in TAG_PATTERN.finditer(text):
        name = match.group(2).lower()

        if not match.group(1):
            stack.append(name)
        elif stack and stack[-1] == name:
            stack.pop()
        else:
            return False

    return not stack


def has_supported_tags(text: str) -> bool:
    """Return True when the text contains at least one supported tag."""
    return TAG_PATTERN.search(text) is not None


def _escape_text(text: str) -> str:
    """Escape text so that Telegram reads it literally."""
    result: list[str] = []
    position = 0

    for match in _ENTITY.finditer(text):
        result.append(_escape_plain(text[position : match.start()]))
        token = match.group(0)

        if token in _TELEGRAM_NAMED_ENTITIES or token[1] == "#":
            result.append(token)
        else:
            decoded = html.unescape(token)
            result.append(
                _escape_plain(decoded) if decoded != token else _escape_plain(token)
            )

        position = match.end()

    result.append(_escape_plain(text[position:]))
    return "".join(result)


def _escape_plain(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _attribute_value(text: str, name: str) -> str | None:
    for match in _ATTRIBUTE.finditer(text):
        if match.group(1).lower() != name:
            continue

        for group in (2, 3, 4):
            if match.group(group) is not None:
                return html.unescape(match.group(group))

        return ""

    return None


def _has_attribute(text: str, name: str) -> bool:
    return any(m.group(1).lower() == name for m in _ATTRIBUTE.finditer(text))


def _quote_value(value: str) -> str:
    return _escape_text(value).replace('"', "&quot;")


def _anchor(raw_attributes: str) -> str | None:
    href = _attribute_value(raw_attributes, "href")

    if href is None or not _SAFE_URL.match(href.strip()):
        return None

    return f'<a href="{_quote_value(href.strip())}">'


def _span(raw_attributes: str) -> str | None:
    css = _attribute_value(raw_attributes, "class")
    return '<span class="tg-spoiler">' if css == "tg-spoiler" else None


def _emoji(raw_attributes: str) -> str | None:
    emoji_id = _attribute_value(raw_attributes, "emoji-id")

    if emoji_id is None or not _DIGITS.match(emoji_id):
        return None

    return f'<tg-emoji emoji-id="{emoji_id}">'


def _code(raw_attributes: str) -> str | None:
    css = _attribute_value(raw_attributes, "class")

    if css is not None and _LANGUAGE_CLASS.match(css):
        return f'<code class="{css}">'

    return "<code>"


def _blockquote(raw_attributes: str) -> str | None:
    if _has_attribute(raw_attributes, "expandable"):
        return "<blockquote expandable>"

    return "<blockquote>"


_OPENERS: dict[str, Callable[[str], str | None]] = {
    "a": _anchor,
    "span": _span,
    "tg-emoji": _emoji,
    "code": _code,
    "blockquote": _blockquote,
}


def _open_tag(name: str, raw_attributes: str) -> str | None:
    """Return a clean opening tag or None when the tag must be dropped."""
    opener = _OPENERS.get(name)
    return f"<{name}>" if opener is None else opener(raw_attributes)


def sanitize_html(text: str) -> str:
    """Return Telegram-safe HTML.

    Supported tags are kept with whitelisted attributes, ``<br>`` becomes a
    newline, everything else is escaped and shown as text.
    """
    text = _BREAK.sub("\n", text)
    result: list[str] = []
    stack: list[tuple[str, bool]] = []
    position = 0

    for match in TAG_PATTERN.finditer(text):
        result.append(_escape_text(text[position : match.start()]))
        position = match.end()
        name = match.group(2).lower()

        if match.group(1):
            if stack and stack[-1][0] == name:
                _, kept = stack.pop()
                if kept:
                    result.append(f"</{name}>")
            else:
                result.append(_escape_text(match.group(0)))
            continue

        opening = _open_tag(name, match.group(3) or "")
        stack.append((name, opening is not None))
        if opening is not None:
            result.append(opening)

    result.append(_escape_text(text[position:]))

    # Close tags that were left open so Telegram never rejects the message.
    result.extend(f"</{name}>" for name, kept in reversed(stack) if kept)
    return "".join(result)


__all__ = [
    "SUPPORTED_TAGS",
    "TAG_PATTERN",
    "has_supported_tags",
    "is_balanced",
    "mask_preformatted",
    "sanitize_html",
]
