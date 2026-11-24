# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Conversion of inline Markdown (emphasis, code spans, links) to MarkdownV2."""

from bot_obormot.services.chat.formatting.markdown_v2.escaping import (
    escape_code,
    escape_text,
    escape_url,
)

_MD_ESCAPABLE = frozenset("\\`*_{}[]()#+-.!|~>=<")
_BACKTICK = "`"
_BACKSLASH = "\\"
_OPEN_BRACKET = "["
_CLOSE_BRACKET = "]"
_OPEN_PAREN = "("
_CLOSE_PAREN = ")"
_TILDE = "~"
_EXCLAMATION = "!"
_STYLE_MARKERS = "*_~"
_LINK_KIND = "link"
_STRIKE_RUN = 2
_KINDS_BY_RUN = {1: ("italic",), 2: ("bold",), 3: ("bold", "italic")}
_SYMBOLS = {"bold": "*", "italic": "_", "strike": "~"}


def _run_length(text: str, index: int) -> int:
    char = text[index]
    end = index
    while end < len(text) and text[end] == char:
        end += 1
    return end - index


def _skip_code_span(text: str, index: int) -> int:
    """Return the index after the code span at *index*, or after its ticks."""
    ticks = _run_length(text, index)
    close = text.find("`" * ticks, index + ticks)
    while close != -1 and (
        (close > 0 and text[close - 1] == _BACKTICK)
        or text[close + ticks : close + ticks + 1] == _BACKTICK
    ):
        close = text.find("`" * ticks, close + 1)
    return index + ticks if close == -1 else close + ticks


def _closing_run(text: str, start: int, marker: str, size: int) -> int:
    """Find the index of a closing run of exactly *size* markers."""
    index = start

    while index < len(text):
        char = text[index]

        if char == _BACKSLASH:
            index += 2
        elif char == _BACKTICK:
            index = _skip_code_span(text, index)
        elif char == marker:
            length = _run_length(text, index)
            after = text[index + length : index + length + 1]
            before = text[index - 1] if index > start else ""
            if (
                length == size
                and before
                and not before.isspace()
                and not after.isalnum()
            ):
                return index
            index += length
        else:
            index += 1

    return -1


def _matching_bracket(text: str, index: int) -> int | None:
    """Return the index of the ``]`` that closes the ``[`` at *index*."""
    depth = 0
    pos = index

    while pos < len(text):
        char = text[pos]
        if char == _BACKSLASH:
            pos += 2
            continue
        if char == _OPEN_BRACKET:
            depth += 1
        elif char == _CLOSE_BRACKET:
            depth -= 1
            if depth == 0:
                return pos
        pos += 1

    return None


def _link_destination(text: str, start: int) -> tuple[str, int] | None:
    """Read ``url`` or ``url "title"`` up to the closing parenthesis."""
    depth = 1
    url_end: int | None = None
    cursor = start

    while cursor < len(text):
        char = text[cursor]
        if char == _OPEN_PAREN:
            depth += 1
        elif char == _CLOSE_PAREN:
            depth -= 1
        elif char.isspace() and depth == 1 and url_end is None:
            url_end = cursor

        if char == _CLOSE_PAREN and depth == 0:
            end = cursor if url_end is None else url_end
            return text[start:end], cursor + 1

        cursor += 1

    return None


def _find_link(text: str, index: int) -> tuple[str, str, int] | None:
    """Parse ``[label](url)`` at *index*; return label, url and the end."""
    close = _matching_bracket(text, index)

    if close is None or text[close + 1 : close + 2] != _OPEN_PAREN:
        return None

    destination = _link_destination(text, close + 2)

    if destination is None:
        return None

    url, end = destination
    return text[index + 1 : close], url, end


def _can_open(text: str, index: int, size: int) -> bool:
    """Check that the marker run at *index* may open an emphasis span."""
    if text[index] == _TILDE:
        valid = size == _STRIKE_RUN
    else:
        before = text[index - 1] if index else ""
        valid = size in _KINDS_BY_RUN and not before.isalnum()

    after = text[index + size : index + size + 1]
    return valid and bool(after) and not after.isspace()


def _emphasis(
    text: str,
    index: int,
    active: frozenset[str],
) -> tuple[str, int] | None:
    """Try to read an emphasis span at *index*."""
    size = _run_length(text, index)

    if not _can_open(text, index, size):
        return None

    marker = text[index]
    closer = _closing_run(text, index + size, marker, size)

    if closer == -1:
        return None

    kinds = ("strike",) if marker == _TILDE else _KINDS_BY_RUN[size]
    content = text[index + size : closer]
    return _wrap(content, kinds, active), closer + size


def _wrap(
    content: str,
    kinds: tuple[str, ...],
    active: frozenset[str],
) -> str:
    """Render *content* inside the given emphasis kinds."""
    inner = render_inline(content, active | frozenset(kinds))

    if not inner.strip():
        return inner

    for kind in reversed(kinds):
        if kind not in active:
            symbol = _SYMBOLS[kind]
            inner = f"{symbol}{inner}{symbol}"

    return inner


def _code_span(text: str, index: int) -> tuple[str, int] | None:
    ticks = _run_length(text, index)
    end = _skip_code_span(text, index)

    if end == index + ticks:
        return None

    content = text[index + ticks : end - ticks]
    if content.startswith(" ") and content.endswith(" ") and content.strip():
        content = content[1:-1]

    if not content:
        return None

    return f"`{escape_code(content)}`", end


def _link_text(
    label: str,
    url: str,
    *,
    is_image: bool,
    active: frozenset[str],
) -> str:
    """Render the visible text of a link or an image."""
    if label.strip():
        return render_inline(label, active | {_LINK_KIND})

    return escape_text("image" if is_image else url)


def _link(
    text: str,
    index: int,
    active: frozenset[str],
) -> tuple[str, int] | None:
    is_image = text[index] == _EXCLAMATION
    parsed = _find_link(text, index + 1 if is_image else index)

    if parsed is None:
        return None

    label, url, end = parsed
    url = url.strip().strip("<>")

    if not url:
        return None

    shown = _link_text(label, url, is_image=is_image, active=active)

    return f"[{shown}]({escape_url(url)})", end


def render_inline(text: str, active: frozenset[str] = frozenset()) -> str:
    """Convert inline Markdown to MarkdownV2."""
    result: list[str] = []
    index = 0

    while index < len(text):
        char = text[index]
        parsed: tuple[str, int] | None = None

        if char == _BACKSLASH and text[index + 1 : index + 2] in _MD_ESCAPABLE:
            result.append(escape_text(text[index + 1]))
            index += 2
            continue

        if char == _BACKTICK:
            parsed = _code_span(text, index)
        elif char in _STYLE_MARKERS:
            parsed = _emphasis(text, index, active)
        elif (
            char == _OPEN_BRACKET or text.startswith("![", index)
        ) and _LINK_KIND not in active:
            parsed = _link(text, index, active)

        if parsed is not None:
            result.append(parsed[0])
            index = parsed[1]
        elif char == _BACKTICK or char in _STYLE_MARKERS:
            run = _run_length(text, index)
            result.append(escape_text(text[index : index + run]))
            index += run
        else:
            result.append(escape_text(char))
            index += 1

    return "".join(result)


__all__ = ["render_inline"]
