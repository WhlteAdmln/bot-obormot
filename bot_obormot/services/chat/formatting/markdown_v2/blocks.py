# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Parsing of Markdown blocks (fences, headings, lists, quotes, tables)."""

import re
from collections.abc import Callable

from bot_obormot.services.chat.formatting.markdown_v2.escaping import (
    escape_code,
    escape_text,
)
from bot_obormot.services.chat.formatting.markdown_v2.inline import render_inline

_FENCE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[ \t]*([^\s`]*)[^\n]*$")
_HEADING = re.compile(r"^[ ]{0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_RULE = re.compile(r"^[ ]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$")
_QUOTE = re.compile(r"^[ ]{0,3}>[ ]?(.*)$")
_BULLET = re.compile(r"^([ \t]*)[-*+][ \t]+(.*)$")
_NUMBERED = re.compile(r"^([ \t]*)(\d{1,9})([.)])[ \t]+(.*)$")
_TASK = re.compile(r"^\[([ xX])\][ \t]+(.*)$")
_TABLE_ROW = re.compile(r"^[ ]{0,3}\|.*\|[ \t]*$")
_LANGUAGE = re.compile(r"^[A-Za-z0-9_+#.-]{1,32}$")
_RULE_TEXT = "──────────"
_SPACE = " "
_BlockParser = Callable[[list[str], int], tuple[str, int] | None]


def _list_line(line: str) -> str | None:
    bullet = _BULLET.match(line)
    if bullet:
        indent, rest = bullet.groups()
        task = _TASK.match(rest)
        if task:
            mark = "☐" if task.group(1) == _SPACE else "☑"
            return f"{indent}{mark} {render_inline(task.group(2))}"
        return f"{indent}• {render_inline(rest)}"

    numbered = _NUMBERED.match(line)
    if numbered:
        indent, number, delimiter, rest = numbered.groups()
        return f"{indent}{number}{escape_text(delimiter)} {render_inline(rest)}"

    return None


def _parse_fence(lines: list[str], index: int) -> tuple[str, int] | None:
    match = _FENCE.match(lines[index])

    if match is None:
        return None

    fence, language = match.group(1), match.group(2)
    closing = re.compile(rf"^[ ]{{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$")
    body: list[str] = []
    cursor = index + 1

    while cursor < len(lines) and not closing.match(lines[cursor]):
        body.append(lines[cursor])
        cursor += 1

    header = f"```{language}" if _LANGUAGE.match(language) else "```"
    content = escape_code("\n".join(body))
    return f"{header}\n{content}\n```", min(cursor + 1, len(lines))


def _parse_heading(lines: list[str], index: int) -> tuple[str, int] | None:
    match = _HEADING.match(lines[index])

    if match is None:
        return None

    title = render_inline(match.group(1), frozenset({"bold"}))
    return (f"*{title}*" if title.strip() else ""), index + 1


def _parse_rule(lines: list[str], index: int) -> tuple[str, int] | None:
    return (_RULE_TEXT, index + 1) if _RULE.match(lines[index]) else None


def _parse_table(lines: list[str], index: int) -> tuple[str, int] | None:
    """Render a table as a code block, because Telegram has no tables."""
    if not _TABLE_ROW.match(lines[index]):
        return None

    rows: list[str] = []
    while index < len(lines) and _TABLE_ROW.match(lines[index]):
        rows.append(lines[index].strip())
        index += 1

    return f"```\n{escape_code(chr(10).join(rows))}\n```", index


def _parse_quote(lines: list[str], index: int) -> tuple[str, int] | None:
    if not _QUOTE.match(lines[index]):
        return None

    quoted: list[str] = []
    while index < len(lines) and (match := _QUOTE.match(lines[index])):
        quoted.append(f">{render_inline(match.group(1))}")
        index += 1

    return "\n".join(quoted), index


def _parse_list(lines: list[str], index: int) -> tuple[str, int] | None:
    first = _list_line(lines[index])

    if first is None:
        return None

    items = [first]
    index += 1
    while index < len(lines) and (item := _list_line(lines[index])) is not None:
        items.append(item)
        index += 1

    return "\n".join(items), index


_BLOCK_PARSERS: tuple[_BlockParser, ...] = (
    _parse_fence,
    _parse_heading,
    _parse_rule,
    _parse_table,
    _parse_quote,
    _parse_list,
)


def _is_block_start(lines: list[str], index: int) -> bool:
    return any(parser(lines, index) is not None for parser in _BLOCK_PARSERS)


def _parse_paragraph(lines: list[str], index: int) -> tuple[str, int]:
    """Collect lines until a blank line or the start of another block."""
    paragraph = [lines[index]]
    index += 1

    while (
        index < len(lines)
        and lines[index].strip()
        and not _is_block_start(lines, index)
    ):
        paragraph.append(lines[index])
        index += 1

    return render_inline("\n".join(paragraph)), index


def next_block(lines: list[str], index: int) -> tuple[str, int]:
    """Render the block that starts at *index*; return it and the next index."""
    for parser in _BLOCK_PARSERS:
        parsed = parser(lines, index)
        if parsed is not None:
            return parsed

    return _parse_paragraph(lines, index)


__all__ = ["next_block"]
