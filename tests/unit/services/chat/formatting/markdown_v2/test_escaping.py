# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for MarkdownV2 escaping."""

from bot_obormot.services.chat.formatting.markdown_v2.escaping import (
    escape_code,
    escape_text,
    escape_url,
)


def test_escapes_reserved_characters_in_text() -> None:
    text = "Итог: 7+3=10 (почти)!"
    expected = "Итог: 7\\+3\\=10 \\(почти\\)\\!"

    assert escape_text(text) == expected, "reserved characters are not escaped"


def test_escapes_backslash_and_backtick_in_code() -> None:
    code = "path = 'C:\\tmp' + `ls`"
    expected = "path = 'C:\\\\tmp' + \\`ls\\`"

    assert escape_code(code) == expected, "code escaping is wrong"


def test_escapes_closing_parenthesis_in_url() -> None:
    url = "https://wiki.example.org/Kotlin_(язык)"
    expected = "https://wiki.example.org/Kotlin_(язык\\)"

    assert escape_url(url) == expected, "URL escaping is wrong"
