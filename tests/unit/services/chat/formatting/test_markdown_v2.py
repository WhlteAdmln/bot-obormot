# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting markdown v2."""

import pytest

from bot_obormot.services.chat.formatting import (
    to_markdown_v2,
)


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
    assert to_markdown_v2(text) == expected


def test_code_block_content_is_not_interpreted_as_markup() -> None:
    text = "```\n**не жирный** _не курсив_ # не заголовок\n```"

    assert to_markdown_v2(text) == text
