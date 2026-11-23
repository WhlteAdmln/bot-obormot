# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for text utils."""

from bot_obormot.common.text import log_safe, utf16_length


def test_log_safe_escapes_line_breaks_and_truncates_values() -> None:
    """Log safe escapes line breaks and truncates values."""
    expected_log_safe = "a\\nERROR fake"
    assert log_safe("a\nERROR fake") == expected_log_safe
    expected_log_safe = "a\\rERROR fake"
    assert log_safe("a\rERROR fake") == expected_log_safe
    expected_log_safe = "a?b"
    assert log_safe("a\x00b") == expected_log_safe
    expected_log_safe = "abcde"
    assert log_safe("abcdefgh", limit=5) == expected_log_safe
    expected_empty = ""
    assert log_safe(None) == expected_empty, "expected an empty string"


def test_utf16_length_counts_code_units() -> None:
    """UTF-16 length counts supplementary characters as two units."""
    expected_utf16_length = 3
    assert utf16_length("a😀") == expected_utf16_length
