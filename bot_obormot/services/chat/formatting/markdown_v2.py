# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Conversion of common Markdown into Telegram MarkdownV2."""

import re
from collections.abc import Callable

_RESERVED = frozenset("_*[]()~`>#+-=|{}.!\\")
_MD_ESCAPABLE = frozenset("\\`*_{}[]()#+-.!|~>=<")

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

_STRIKE_RUN = 2
_KINDS_BY_RUN = {1: ("italic",), 2: ("bold",), 3: ("bold", "italic")}
_SYMBOLS = {"bold": "*", "italic": "_", "strike": "~"}

_BlockParser = Callable[[list[str], int], tuple[str, int] | None]


def escape_text(text: str) -> str:
    """Escape characters reserved by MarkdownV2 outside of code."""
    return "".join(f"\\{c}" if c in _RESERVED else c for c in text)


def _escape_code(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _escape_url(text: str) -> str:
    return text.replace("\\", "\\\\").replace(")", "\\)")


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
        (close > 0 and text[close - 1] == "`")
        or text[close + ticks : close + ticks + 1] == "`"
    ):
        close = text.find("`" * ticks, close + 1)
    return index + ticks if close == -1 else close + ticks


def _closing_run(text: str, start: int, marker: str, size: int) -> int:
    """Find the index of a closing run of exactly *size* markers."""
    index = start

    while index < len(text):
        char = text[index]

        if char == "\\":
            index += 2
        elif char == "`":
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
        if char == "\\":
            pos += 2
            continue
        if char == "[":
            depth += 1
        elif char == "]":
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
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char.isspace() and depth == 1 and url_end is None:
            url_end = cursor

        if char == ")" and depth == 0:
            end = cursor if url_end is None else url_end
            return text[start:end], cursor + 1

        cursor += 1

    return None


def _find_link(text: str, index: int) -> tuple[str, str, int] | None:
    """Parse ``[label](url)`` at *index*; return label, url and the end."""
    close = _matching_bracket(text, index)

    if close is None or text[close + 1 : close + 2] != "(":
        return None

    destination = _link_destination(text, close + 2)

    if destination is None:
        return None

    url, end = destination
    return text[index + 1 : close], url, end


def _can_open(text: str, index: int, size: int) -> bool:
    """Check that the marker run at *index* may open an emphasis span."""
    if text[index] == "~":
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

    kinds = ("strike",) if marker == "~" else _KINDS_BY_RUN[size]
    content = text[index + size : closer]
    return _wrap(content, kinds, active), closer + size


def _wrap(
    content: str,
    kinds: tuple[str, ...],
    active: frozenset[str],
) -> str:
    """Render *content* inside the given emphasis kinds."""
    inner = _inline(content, active | frozenset(kinds))

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

    return f"`{_escape_code(content)}`", end


def _link(
    text: str,
    index: int,
    active: frozenset[str],
) -> tuple[str, int] | None:
    is_image = text[index] == "!"
    parsed = _find_link(text, index + 1 if is_image else index)

    if parsed is None:
        return None

    label, url, end = parsed
    url = url.strip().strip("<>")

    if not url:
        return None

    # A nested ternary here would be harder to read than the two branches.
    if label.strip():  # pylint: disable=consider-ternary-expression
        shown = _inline(label, active | {"link"})
    else:
        shown = escape_text("image" if is_image else url)

    return f"[{shown}]({_escape_url(url)})", end


def _inline(text: str, active: frozenset[str] = frozenset()) -> str:
    """Convert inline Markdown to MarkdownV2."""
    result: list[str] = []
    index = 0

    while index < len(text):
        char = text[index]
        parsed: tuple[str, int] | None = None

        if char == "\\" and text[index + 1 : index + 2] in _MD_ESCAPABLE:
            result.append(escape_text(text[index + 1]))
            index += 2
            continue

        if char == "`":
            parsed = _code_span(text, index)
        elif char in "*_~":
            parsed = _emphasis(text, index, active)
        elif (char == "[" or text.startswith("![", index)) and "link" not in active:
            parsed = _link(text, index, active)

        if parsed is not None:
            result.append(parsed[0])
            index = parsed[1]
        elif char == "`" or char in "*_~":
            run = _run_length(text, index)
            result.append(escape_text(text[index : index + run]))
            index += run
        else:
            result.append(escape_text(char))
            index += 1

    return "".join(result)


def _list_line(line: str) -> str | None:
    bullet = _BULLET.match(line)
    if bullet:
        indent, rest = bullet.groups()
        task = _TASK.match(rest)
        if task:
            mark = "☐" if task.group(1) == " " else "☑"
            return f"{indent}{mark} {_inline(task.group(2))}"
        return f"{indent}• {_inline(rest)}"

    numbered = _NUMBERED.match(line)
    if numbered:
        indent, number, delimiter, rest = numbered.groups()
        return f"{indent}{number}{escape_text(delimiter)} {_inline(rest)}"

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
    content = _escape_code("\n".join(body))
    return f"{header}\n{content}\n```", min(cursor + 1, len(lines))


def _parse_heading(lines: list[str], index: int) -> tuple[str, int] | None:
    match = _HEADING.match(lines[index])

    if match is None:
        return None

    title = _inline(match.group(1), frozenset({"bold"}))
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

    return f"```\n{_escape_code(chr(10).join(rows))}\n```", index


def _parse_quote(lines: list[str], index: int) -> tuple[str, int] | None:
    if not _QUOTE.match(lines[index]):
        return None

    quoted: list[str] = []
    while index < len(lines) and (match := _QUOTE.match(lines[index])):
        quoted.append(f">{_inline(match.group(1))}")
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

    return _inline("\n".join(paragraph)), index


def _next_block(lines: list[str], index: int) -> tuple[str, int]:
    for parser in _BLOCK_PARSERS:
        parsed = parser(lines, index)
        if parsed is not None:
            return parsed

    return _parse_paragraph(lines, index)


def to_markdown_v2(text: str) -> str:
    """Convert Markdown (as written by LLMs) into Telegram MarkdownV2."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        if lines[index].strip():
            block, index = _next_block(lines, index)
            output.append(block)
            continue

        if output and output[-1]:
            output.append("")
        index += 1

    while output and not output[-1]:
        output.pop()

    return "\n".join(output)


__all__ = ["escape_text", "to_markdown_v2"]
