# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting detect."""

import pytest

from bot_obormot.services.chat.formatting import (
    detect_format,
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
def test_detects_text_format(text: str, expected: str) -> None:
    assert detect_format(text) == expected
