# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting prepare."""

from bot_obormot.common.text import utf16_length
from bot_obormot.services.chat.formatting import (
    prepare_response,
)


def test_prepare_response_uses_matching_parse_mode_and_keeps_original() -> None:
    markdown, html_chunk, plain = (
        prepare_response("**a** b.c")[0],
        prepare_response("<b>a</b> b&c")[0],
        prepare_response("a *b")[0],
    )

    assert (markdown.parse_mode, markdown.text) == ("MarkdownV2", "*a* b\\.c")
    expected_plain_text = "**a** b.c"
    assert markdown.plain_text == expected_plain_text
    assert (html_chunk.parse_mode, html_chunk.text) == ("HTML", "<b>a</b> b&amp;c")
    expected_plain_text = "<b>a</b> b&c"
    assert html_chunk.plain_text == expected_plain_text
    assert (plain.parse_mode, plain.text) == (None, "a *b")


def test_prepare_response_ignores_empty_text() -> None:
    assert prepare_response("  \n ") == []


def test_prepare_response_respects_the_length_limit() -> None:
    text = "**начало**\n\n" + "\n\n".join(["слово " * 100] * 30)

    chunks = prepare_response(text, 500)

    assert len(chunks) > 1
    expected_utf16_length = 500
    assert all(
        utf16_length(chunk.plain_text) <= expected_utf16_length for chunk in chunks
    )
    expected_parse_mode = "MarkdownV2"
    assert all(chunk.parse_mode == expected_parse_mode for chunk in chunks)


def test_prepare_response_keeps_html_valid_after_splitting() -> None:
    text = '<a href="https://e.com">' + "слово " * 30 + "</a>"

    chunks = prepare_response(text, 40)

    assert len(chunks) > 1
    expected_parse_mode = "HTML"
    assert all(chunk.parse_mode == expected_parse_mode for chunk in chunks)
    assert all(
        chunk.text.startswith('<a href="https://e.com">')
        and chunk.text.endswith("</a>")
        for chunk in chunks
    )
