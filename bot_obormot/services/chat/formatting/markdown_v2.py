# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Conversion of common Markdown into Telegram MarkdownV2."""

import re

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


def escape_text(text: str) -> str:
    """Escape characters reserved by MarkdownV2 outside of code."""
    return "".join(f"\\{c}" if c in _RESERVED else c for c in text)


def _escape_code(text: str) -> str:
    return text.replace("\\", "\\\\").replace("`", "\\`")


def _escape_url(text: str) -> str:
    return text.replace("\\", "\\\\").replace(")", "\\)")


def _is_escaped(text: str, index: int) -> bool:
    backslashes = 0
    while index - 1 - backslashes >= 0 and text[index - 1 - backslashes] == "\\":
        backslashes += 1
    return backslashes % 2 == 1


def _run_length(text: str, index: int) -> int:
    char = text[index]
    end = index
    while end < len(text) and text[end] == char:
        end += 1
    return end - index


def _skip_code_span(text: str, index: int) -> int:
    """Return the index after a code span starting at *index* or *index*."""
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
            closes = (
                length == size
                and before != ""
                and not before.isspace()
                and not after.isalnum()
            )
            if closes:
                return index
            index += length
        else:
            index += 1

    return -1


def _find_link(text: str, index: int) -> tuple[str, str, int] | None:
    """Parse ``[label](url)`` at *index*; return label, url and the end."""
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
                break
        pos += 1
    else:
        return None

    if text[pos + 1 : pos + 2] != "(":
        return None

    label = text[index + 1 : pos]
    url_start = pos + 2
    parens = 1
    cursor = url_start

    while cursor < len(text) and parens:
        if text[cursor] == "(":
            parens += 1
        elif text[cursor] == ")":
            parens -= 1
        elif text[cursor].isspace() and parens == 1:
            break
        cursor += 1

    if parens != 0 and not text[cursor - 1 : cursor] == ")":
        # Allow an optional title: [a](url "title")
        close = text.find(")", cursor)
        if close == -1:
            return None
        url = text[url_start:cursor]
        return label, url, close + 1

    return label, text[url_start : cursor - 1], cursor


_KINDS = {"*": ("bold", "italic"), "_": ("bold", "italic")}


def _emphasis(text: str, index: int, active: frozenset[str]) -> tuple[str, int] | None:
    """Try to read an emphasis span at *index*."""
    char = text[index]
    size = _run_length(text, index)
    before = text[index - 1] if index > 0 else ""

    if char == "~":
        if size != 2:
            return None
    elif before.isalnum() or size > 3:
        return None

    after = text[index + size : index + size + 1]
    if not after or after.isspace():
        return None

    closer = _closing_run(text, index + size, char, size)
    if closer == -1:
        return None

    content = text[index + size : closer]
    end = closer + size

    if char == "~":
        return _wrap(content, ("strike",), "~", active), end

    kinds = {1: ("italic",), 2: ("bold",), 3: ("bold", "italic")}[size]
    return _wrap(content, kinds, "", active), end


def _wrap(content: str, kinds: tuple[str, ...], _mark: str, active: frozenset[str]) -> str:
    inner_active = active | frozenset(kinds)
    inner = _inline(content, inner_active)

    if not inner.strip():
        return inner

    symbols = {"bold": "*", "italic": "_", "strike": "~"}

    for kind in reversed(kinds):
        if kind in active:
            continue
        symbol = symbols[kind]
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


def _link(text: str, index: int, active: frozenset[str]) -> tuple[str, int] | None:
    is_image = text[index] == "!"
    start = index + 1 if is_image else index
    parsed = _find_link(text, start)

    if parsed is None:
        return None

    label, url, end = parsed
    url = url.strip().strip("<>")

    if not url:
        return None

    shown = _inline(label, active | {"link"}) if label.strip() else escape_text(url)
    if is_image and not label.strip():
        shown = escape_text("image")

    return f"[{shown}]({_escape_url(url)})", end


def _inline(text: str, active: frozenset[str] = frozenset()) -> str:
    """Convert inline Markdown to MarkdownV2."""
    result: list[str] = []
    index = 0

    while index < len(text):
        char = text[index]
        parsed: tuple[str, int] | None = None

        if char == "\\" and index + 1 < len(text):
            following = text[index + 1]
            if following in _MD_ESCAPABLE:
                result.append(escape_text(following))
                index += 2
                continue
        elif char == "`":
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


def _fenced_block(lines: list[str], index: int) -> tuple[str, int]:
    match = _FENCE.match(lines[index])
    assert match is not None  # noqa: S101 - callers check the fence first
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


def _is_block_start(line: str) -> bool:
    return bool(
        _FENCE.match(line)
        or _HEADING.match(line)
        or _RULE.match(line)
        or _QUOTE.match(line)
        or _BULLET.match(line)
        or _NUMBERED.match(line)
        or _TABLE_ROW.match(line)
    )


def to_markdown_v2(text: str) -> str:  # noqa: C901, PLR0912
    """Convert Markdown (as written by LLMs) into Telegram MarkdownV2."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    output: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            output.append(_inline("\n".join(paragraph)))
            paragraph.clear()

    while index < len(lines):
        line = lines[index]

        if _FENCE.match(line):
            flush_paragraph()
            block, index = _fenced_block(lines, index)
            output.append(block)
            continue

        if not line.strip():
            flush_paragraph()
            if output and output[-1] != "":
                output.append("")
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            title = _inline(heading.group(1), frozenset({"bold"}))
            output.append(f"*{title}*" if title.strip() else "")
            index += 1
            continue

        if _RULE.match(line):
            flush_paragraph()
            output.append(_RULE_TEXT)
            index += 1
            continue

        if _TABLE_ROW.match(line):
            flush_paragraph()
            rows = []
            while index < len(lines) and _TABLE_ROW.match(lines[index]):
                rows.append(lines[index].strip())
                index += 1
            output.append(f"```\n{_escape_code(chr(10).join(rows))}\n```")
            continue

        if _QUOTE.match(line):
            flush_paragraph()
            quoted = []
            while index < len(lines) and (match := _QUOTE.match(lines[index])):
                quoted.append(f">{_inline(match.group(1))}")
                index += 1
            output.append("\n".join(quoted))
            continue

        converted = _list_line(line)
        if converted is not None:
            flush_paragraph()
            output.append(converted)
            index += 1
            # Keep consecutive list items together without blank lines.
            while index < len(lines) and (item := _list_line(lines[index])):
                output[-1] += "\n" + item
                index += 1
            continue

        paragraph.append(line)
        index += 1

        while (
            index < len(lines)
            and lines[index].strip()
            and not _is_block_start(lines[index])
        ):
            paragraph.append(lines[index])
            index += 1

    flush_paragraph()

    while output and output[-1] == "":
        output.pop()

    return "\n".join(output)


__all__ = ["escape_text", "to_markdown_v2"]
