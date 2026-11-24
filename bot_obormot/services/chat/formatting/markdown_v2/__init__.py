# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Conversion of common Markdown into Telegram MarkdownV2."""

from bot_obormot.services.chat.formatting.markdown_v2.blocks import next_block
from bot_obormot.services.chat.formatting.markdown_v2.escaping import escape_text


def to_markdown_v2(text: str) -> str:
    """Convert Markdown (as written by LLMs) into Telegram MarkdownV2."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip().split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        if lines[index].strip():
            block, index = next_block(lines, index)
            output.append(block)
            continue

        if output and output[-1]:
            output.append("")
        index += 1

    while output and not output[-1]:
        output.pop()

    return "\n".join(output)


__all__ = ["escape_text", "to_markdown_v2"]
