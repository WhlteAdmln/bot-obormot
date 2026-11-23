# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting text splitter."""

import pytest

from bot_obormot.common.text import utf16_length
from bot_obormot.services.chat.formatting import (
    split_markdown_message,
    split_plain_message,
)


def test_markdown_splitter_reopens_fenced_code_in_every_part() -> None:
    """Close and reopen a fence when a code block must be split."""
    code = "\n".join(f"line{i}" for i in range(40))

    chunks = split_markdown_message(f"текст\n\n```py\n{code}\n```", 80)

    code_parts = [chunk for chunk in chunks if chunk.startswith("```py")]
    assert len(code_parts) > 1
    assert all(chunk.endswith("```") for chunk in code_parts)
    expected_utf16_length = 80
    assert all(utf16_length(chunk) <= expected_utf16_length for chunk in chunks)


def test_markdown_splitter_preserves_block_separators() -> None:
    """Keep the original blank lines inside one part."""
    assert split_markdown_message("a\n\nb\n\n\nc", 100) == ["a\n\nb\n\n\nc"]


def test_plain_splitter_cuts_long_text_on_word_boundaries() -> None:
    """Split plain text by words and respect the UTF-16 limit."""
    chunks = split_plain_message("слово " * 10, 20)

    assert chunks == ["слово слово слово"] * 3 + ["слово"]


def test_splitters_reject_invalid_limit() -> None:
    """Reject a non-positive limit."""
    with pytest.raises(ValueError, match="greater than zero"):
        split_markdown_message("text", 0)


def test_plain_splitter_does_not_treat_fences_as_code() -> None:
    """Split plain text that contains backticks by length only."""
    text = "```\n" + "слово " * 10 + "\n```"

    chunks = split_plain_message(text, 20)

    assert chunks
    expected_utf16_length = 20
    assert all(utf16_length(chunk) <= expected_utf16_length for chunk in chunks)
