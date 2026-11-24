# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for text utils."""

import pytest

from bot_obormot.common.text import log_safe, utf16_length


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("a\nERROR fake", "a\\nERROR fake"),
        ("a\rERROR fake", "a\\rERROR fake"),
        ("a\r\nINFO forged", "a\\r\\nINFO forged"),
        ("a\x00b", "a?b"),
        ("\x1b[31mred\x1b[0m", "?[31mred?[0m"),
        ("tab\there", "tab?here"),
        ("line\u2028separator", "line?separator"),
        ("evil\u202etxt.exe", "evil?txt.exe"),
        (None, ""),
        (4096, "4096"),
        ("Привет, мир", "Привет, мир"),
    ],
    ids=[
        "line-feed",
        "carriage-return",
        "crlf",
        "nul",
        "ansi-escape",
        "tab",
        "unicode-line-separator",
        "bidi-override",
        "none",
        "integer",
        "cyrillic",
    ],
)
def test_log_safe_escapes_characters_that_break_a_log_line(
    value: object, expected: str
) -> None:
    assert log_safe(value) == expected, "the value is not safe for a log line"


@pytest.mark.parametrize(
    ("value", "limit", "expected"),
    [
        ("abcdefgh", 5, "abcde"),
        ("z" * 500, 120, "z" * 120),
        ("\n\n\n", 3, "\\n\\"),
        ("anything", 0, ""),
    ],
    ids=["short-limit", "default-limit", "escape-before-truncation", "zero-limit"],
)
def test_log_safe_truncates_the_escaped_value(
    value: str, limit: int, expected: str
) -> None:
    assert log_safe(value, limit=limit) == expected, "the value is truncated wrongly"


@pytest.mark.parametrize(
    ("text", "expected"),
    [("a😀", 3), ("", 0), ("Ёж", 2), ("👨\u200d👩\u200d👧", 8)],
    ids=["astral", "empty", "cyrillic", "zero-width-joiner"],
)
def test_utf16_length_counts_code_units(text: str, expected: int) -> None:
    assert utf16_length(text) == expected, "the UTF-16 length is wrong"
