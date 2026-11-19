# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Splitting of Markdown and plain text without breaking code blocks."""

import re

from bot_obormot.common.text import utf16_length

_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})[^\n]*$")
_BLANK = re.compile(r"^[ \t]*$")


def _parse_blocks(text: str, *, fences: bool) -> list[tuple[str, str]]:
    """Split text into (block, separator-after) pairs; fenced code stays whole.

    The separator holds the exact newlines that followed the block.
    """
    lines = text.split("\n")
    blocks: list[tuple[str, str]] = []
    current: list[str] = []
    blank_run = 0
    index = 0

    def flush() -> None:
        if current:
            blocks.append(("\n".join(current), "\n"))
            current.clear()

    def start_block() -> None:
        nonlocal blank_run
        if blank_run and blocks:
            blocks[-1] = (blocks[-1][0], "\n" * (blank_run + 1))
        blank_run = 0

    while index < len(lines):
        line = lines[index]
        opening = _FENCE_OPEN.match(line) if fences else None

        if opening:
            flush()
            start_block()
            marker = opening.group(1)
            closing = re.compile(
                rf"^[ ]{{0,3}}{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$"
            )
            end = index + 1
            while end < len(lines) and not closing.match(lines[end]):
                end += 1
            end = min(end, len(lines) - 1)
            current.extend(lines[index : end + 1])
            flush()
            index = end + 1
        elif _BLANK.match(line):
            flush()
            blank_run += 1
            index += 1
        else:
            if not current:
                start_block()
            current.append(line)
            index += 1

    flush()
    return blocks


def _hard_split(text: str, max_length: int) -> list[str]:
    """Split one long line by words, falling back to characters."""
    pieces: list[str] = []
    rest = text

    while utf16_length(rest) > max_length:
        used = 0
        cut = 0

        for position, char in enumerate(rest):
            size = utf16_length(char)
            if used + size > max_length:
                break
            used += size
            cut = position + 1

        # Always make progress, even if one character exceeds the limit.
        cut = max(cut, 1)
        space = rest.rfind(" ", 0, cut)
        if space > cut // 2:
            cut = space + 1

        pieces.append(rest[:cut].rstrip())
        rest = rest[cut:]

    if rest:
        pieces.append(rest)

    return pieces


def _split_lines(block: str, max_length: int) -> list[str]:
    pieces: list[str] = []
    current = ""

    for line in block.split("\n"):
        candidate = f"{current}\n{line}" if current else line

        if utf16_length(candidate) <= max_length:
            current = candidate
            continue

        if current:
            pieces.append(current)
            current = ""

        if utf16_length(line) <= max_length:
            current = line
        else:
            *head, tail = _hard_split(line, max_length)
            pieces.extend(head)
            current = tail

    if current:
        pieces.append(current)

    return pieces


def _split_fenced(block: str, max_length: int) -> list[str]:
    """Split a fenced code block and repeat the fence in every part."""
    lines = block.split("\n")
    opening = lines[0]
    marker_match = _FENCE_OPEN.match(opening)
    marker = marker_match.group(1) if marker_match else "```"
    has_closing = len(lines) > 1 and re.match(
        rf"^[ ]{{0,3}}{re.escape(marker[0])}{{{len(marker)},}}[ \t]*$", lines[-1]
    )
    body = lines[1:-1] if has_closing else lines[1:]
    budget = max_length - utf16_length(opening) - utf16_length(marker) - 2

    if budget < 1:
        return _split_lines(block, max_length)

    parts = _split_lines("\n".join(body), budget) or [""]
    return [f"{opening}\n{part}\n{marker}" for part in parts]


def _split_block(block: str, max_length: int, *, fences: bool) -> list[str]:
    if fences and _FENCE_OPEN.match(block.split("\n", 1)[0]):
        return _split_fenced(block, max_length)
    return _split_lines(block, max_length)


def split_markdown_message(
    text: str,
    max_length: int = 3900,
    *,
    fences: bool = True,
) -> list[str]:
    """Split Markdown (or plain text) into parts of at most *max_length*.

    Parts end at block boundaries where possible. Fenced code blocks are not
    cut in the middle; an oversized block is closed and reopened instead.
    The original text is preserved so that it can be sent as a fallback.
    """
    if max_length < 1:
        msg = "max_length must be greater than zero."
        raise ValueError(msg)

    text = text.replace("\r\n", "\n").strip()

    if not text:
        return []

    chunks: list[str] = []
    current = ""
    pending_separator = ""

    for block, separator in _parse_blocks(text, fences=fences):
        candidate = f"{current}{pending_separator}{block}" if current else block

        if utf16_length(candidate) <= max_length:
            current = candidate
            pending_separator = separator
            continue

        if current:
            chunks.append(current)
            current = ""

        if utf16_length(block) <= max_length:
            current = block
        else:
            *head, tail = _split_block(block, max_length, fences=fences)
            chunks.extend(head)
            current = tail

        pending_separator = separator

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk.strip()]


def split_plain_message(text: str, max_length: int = 3900) -> list[str]:
    """Split plain text into parts of at most *max_length* UTF-16 units."""
    return split_markdown_message(text, max_length, fences=False)


__all__ = ["split_markdown_message", "split_plain_message"]
