# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting prepare."""

import pytest

from bot_obormot.common.text import utf16_length
from bot_obormot.services.chat.formatting import (
    prepare_response,
)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("**a** b.c", ("MarkdownV2", "*a* b\\.c")),
        ("<b>a</b> b&c", ("HTML", "<b>a</b> b&amp;c")),
        ("a *b", (None, "a *b")),
    ],
)
def test_prepare_response_uses_matching_parse_mode(
    source: str, expected: tuple[str | None, str]
) -> None:
    chunk = prepare_response(source)[0]
    assert (chunk.parse_mode, chunk.text) == expected, "wrong parse mode or text"


@pytest.mark.parametrize("source", ["**жирный** конец.точка", "<i>курсив</i> 1&2"])
def test_prepare_response_keeps_original_as_plain_text(source: str) -> None:
    chunk = prepare_response(source)[0]
    assert chunk.plain_text == source, "the plain text differs from the original"


def test_prepare_response_ignores_empty_text() -> None:
    text = "  \n "
    expected_empty: list[object] = []
    assert prepare_response(text) == expected_empty, "empty text produced chunks"


def test_prepare_response_splits_long_text() -> None:
    text = "**начало**\n\n" + "\n\n".join(["слово " * 100] * 30)
    chunks = prepare_response(text, 500)
    assert len(chunks) > 1, "long text was not split"


def test_prepare_response_respects_the_length_limit() -> None:
    limit = 500
    text = "**начало**\n\n" + "\n\n".join(["текст " * 90] * 25)
    chunks = prepare_response(text, limit)
    lengths = [utf16_length(chunk.plain_text) for chunk in chunks]
    assert max(lengths) <= limit, "a chunk is longer than the limit"


def test_prepare_response_keeps_markdown_in_every_chunk() -> None:
    text = "**начало**\n\n" + "\n\n".join(["фраза " * 110] * 20)
    chunks = prepare_response(text, 500)
    expected_modes = {"MarkdownV2"}
    modes = {chunk.parse_mode for chunk in chunks}
    assert modes == expected_modes, "a chunk lost the MarkdownV2 parse mode"


def test_prepare_response_splits_long_html() -> None:
    text = '<a href="https://e.com">' + "слово " * 30 + "</a>"
    chunks = prepare_response(text, 40)
    assert len(chunks) > 1, "long HTML was not split"


def test_prepare_response_keeps_html_in_every_chunk() -> None:
    text = '<a href="https://e.com">' + "ссылка " * 28 + "</a>"
    chunks = prepare_response(text, 40)
    expected_modes = {"HTML"}
    modes = {chunk.parse_mode for chunk in chunks}
    assert modes == expected_modes, "a chunk lost the HTML parse mode"


def test_prepare_response_keeps_html_valid_after_splitting() -> None:
    opening = '<a href="https://e.com">'
    closing = "</a>"
    text = opening + "слово " * 33 + closing
    chunks = prepare_response(text, 40)
    broken = [
        chunk.text
        for chunk in chunks
        if not (chunk.text.startswith(opening) and chunk.text.endswith(closing))
    ]
    expected_empty: list[str] = []
    assert broken == expected_empty, "a chunk is not wrapped in the link tag"
