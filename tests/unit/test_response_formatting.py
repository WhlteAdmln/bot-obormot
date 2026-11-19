# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for format detection, conversion and preparation of LLM responses."""

import pytest

from bot_obormot.common.text import utf16_length
from bot_obormot.services.chat.formatting import (
    detect_format,
    prepare_response,
    sanitize_html,
    split_formatted_message,
    split_markdown_message,
    split_plain_message,
    to_markdown_v2,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Привет, как дела?", "plain"),
        ("Привет **мир**", "markdown"),
        ("*действие* и слово", "markdown"),
        ("# Заголовок", "markdown"),
        ("Список:\n- один\n- два", "markdown"),
        ("запусти `ls -la`", "markdown"),
        ("[ссылка](https://example.com)", "markdown"),
        ("<b>жирный</b> текст", "html"),
        ('<a href="https://example.com">ссылка</a>', "html"),
        ("<pre>x **y**</pre>", "html"),
        ("<b>жирный</b> и **markdown**", "plain"),
        ("<b>не закрыт", "plain"),
        ("</b>сначала закрыт<b>", "plain"),
        ("a < b and c > d", "plain"),
        ("snake_case_name и 2 * 3 * 4", "plain"),
        ("Vector<int> и **жирный**", "markdown"),
        ("```py\nx = '<b>a</b>'\n```", "markdown"),
        ("```\n**a**\n```\n<b>x</b>", "plain"),
    ],
)
def test_detect_format(text: str, expected: str) -> None:
    """Detect Markdown, HTML, plain text and ambiguous mixtures."""
    assert detect_format(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**жирный**", "*жирный*"),
        ("*курсив* и _тоже_", "_курсив_ и _тоже_"),
        ("***оба***", "*_оба_*"),
        ("~~убрано~~", "~убрано~"),
        ("**жир *вложено* текст**", "*жир _вложено_ текст*"),
        ("snake_case_name", "snake\\_case\\_name"),
        ("**не закрыто", "\\*\\*не закрыто"),
        ("2 * 3", "2 \\* 3"),
        ("Цена: $5.00 (скидка!)", "Цена: $5\\.00 \\(скидка\\!\\)"),
        ("# Заголовок", "*Заголовок*"),
        ("- один\n1. два", "• один\n1\\. два"),
        ("> цитата", ">цитата"),
        ("[a](https://e.com/x_(y))", "[a](https://e.com/x_(y\\))"),
        ("`код *не* трогать`", "`код *не* трогать`"),
        ("```py\nprint('a`b')\n```", "```py\nprint('a\\`b')\n```"),
        ("| a | b |\n|---|---|", "```\n| a | b |\n|---|---|\n```"),
    ],
)
def test_markdown_is_converted_to_markdown_v2(text: str, expected: str) -> None:
    """Convert common Markdown and escape reserved characters."""
    assert to_markdown_v2(text) == expected


def test_code_block_content_is_not_interpreted_as_markup() -> None:
    """Keep the content of fenced code untouched except for required escapes."""
    text = "```\n**не жирный** _не курсив_ # не заголовок\n```"

    assert to_markdown_v2(text) == text


def test_sanitize_html_keeps_supported_tags_and_escapes_the_rest() -> None:
    """Keep whitelisted tags and attributes; escape everything else."""
    text = (
        '<b>x</b> a<br>b & <a href="javascript:x">l</a> '
        '<a href="https://e.com?a=1&b=2">ok</a> '
        '<code class="language-py">c</code> <span>n</span> 1<2'
    )

    assert sanitize_html(text) == (
        "<b>x</b> a\nb &amp; l "
        '<a href="https://e.com?a=1&amp;b=2">ok</a> '
        '<code class="language-py">c</code> n 1&lt;2'
    )


def test_prepare_response_uses_matching_parse_mode_and_keeps_original() -> None:
    """Return the parse mode and the unchanged text for the fallback."""
    markdown, html_chunk, plain = (
        prepare_response("**a** b.c")[0],
        prepare_response("<b>a</b> b&c")[0],
        prepare_response("a *b")[0],
    )

    assert (markdown.parse_mode, markdown.text) == ("MarkdownV2", "*a* b\\.c")
    assert markdown.plain_text == "**a** b.c"
    assert (html_chunk.parse_mode, html_chunk.text) == ("HTML", "<b>a</b> b&amp;c")
    assert html_chunk.plain_text == "<b>a</b> b&c"
    assert (plain.parse_mode, plain.text) == (None, "a *b")


def test_prepare_response_ignores_empty_text() -> None:
    """Return no chunks for an empty response."""
    assert prepare_response("  \n ") == []


def test_prepare_response_respects_the_length_limit() -> None:
    """Keep every part of a long Markdown response within the limit."""
    text = "**начало**\n\n" + "\n\n".join(["слово " * 100] * 30)

    chunks = prepare_response(text, 500)

    assert len(chunks) > 1
    assert all(utf16_length(chunk.plain_text) <= 500 for chunk in chunks)
    assert all(chunk.parse_mode == "MarkdownV2" for chunk in chunks)


def test_markdown_splitter_reopens_fenced_code_in_every_part() -> None:
    """Close and reopen a fence when a code block must be split."""
    code = "\n".join(f"line{i}" for i in range(40))

    chunks = split_markdown_message(f"текст\n\n```py\n{code}\n```", 80)

    code_parts = [chunk for chunk in chunks if chunk.startswith("```py")]
    assert len(code_parts) > 1
    assert all(chunk.endswith("```") for chunk in code_parts)
    assert all(utf16_length(chunk) <= 80 for chunk in chunks)


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
    assert all(utf16_length(chunk) <= 20 for chunk in chunks)


def test_html_splitter_treats_a_lone_angle_bracket_as_text() -> None:
    """Do not fail on a bare "<" inside Telegram HTML."""
    assert split_formatted_message("<b>a < b</b>", max_length=100) == ["<b>a < b</b>"]


def test_prepare_response_keeps_html_valid_after_splitting() -> None:
    """Close and reopen tags with attributes in every HTML part."""
    text = '<a href="https://e.com">' + "слово " * 30 + "</a>"

    chunks = prepare_response(text, 40)

    assert len(chunks) > 1
    assert all(chunk.parse_mode == "HTML" for chunk in chunks)
    assert all(
        chunk.text.startswith('<a href="https://e.com">')
        and chunk.text.endswith("</a>")
        for chunk in chunks
    )
