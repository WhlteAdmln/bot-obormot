# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting text splitter."""

import pytest

from bot_obormot.common.text import utf16_length
from bot_obormot.services.chat.formatting import (
    split_markdown_message,
    split_plain_message,
)


def _fenced_code_chunks(line_count: int, limit: int) -> list[str]:
    code = "\n".join(f"line{index}" for index in range(line_count))
    return split_markdown_message(f"текст\n\n```py\n{code}\n```", limit)


def test_markdown_splitter_splits_long_fenced_code_into_parts() -> None:
    chunks = _fenced_code_chunks(40, 80)

    code_parts = [chunk for chunk in chunks if chunk.startswith("```py")]
    minimum_parts = 2
    assert len(code_parts) >= minimum_parts, "the fenced code was not split"


def test_markdown_splitter_reopens_fenced_code_in_every_part() -> None:
    chunks = _fenced_code_chunks(37, 80)

    code_parts = [chunk for chunk in chunks if chunk.startswith("```py")]
    unclosed = [chunk for chunk in code_parts if not chunk.endswith("```")]
    expected_empty: list[str] = []
    assert unclosed == expected_empty, "a code part was not closed"


def test_markdown_splitter_keeps_fenced_code_parts_within_the_limit() -> None:
    limit = 80
    chunks = _fenced_code_chunks(43, limit)

    oversized = [chunk for chunk in chunks if utf16_length(chunk) > limit]
    expected_empty: list[str] = []
    assert oversized == expected_empty, "a part exceeds the limit"


def test_markdown_splitter_preserves_block_separators() -> None:
    text = "a\n\nb\n\n\nc"

    chunks = split_markdown_message(text, 100)

    expected = [text]
    assert chunks == expected, "the block separators changed"


def test_plain_splitter_cuts_long_text_on_word_boundaries() -> None:
    chunks = split_plain_message("слово " * 10, 20)

    expected = ["слово слово слово"] * 3 + ["слово"]
    assert chunks == expected, "the text was not cut on word boundaries"


def test_splitters_reject_invalid_limit() -> None:
    with pytest.raises(ValueError, match="greater than zero") as excinfo:
        split_markdown_message("text", 0)

    assert excinfo.type is ValueError, "a zero limit was accepted"


def test_plain_splitter_returns_parts_for_fenced_text() -> None:
    text = "```\n" + "слово " * 10 + "\n```"

    chunks = split_plain_message(text, 20)

    expected_empty: list[str] = []
    assert chunks != expected_empty, "fenced text produced no parts"


def test_plain_splitter_does_not_treat_fences_as_code() -> None:
    limit = 20
    text = "```\n" + "буква " * 11 + "\n```"

    chunks = split_plain_message(text, limit)

    oversized = [chunk for chunk in chunks if utf16_length(chunk) > limit]
    expected_empty: list[str] = []
    assert oversized == expected_empty, "a part exceeds the limit"
