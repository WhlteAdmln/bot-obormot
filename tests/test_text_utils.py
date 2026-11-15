# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for text utils."""

from bot.utils.text import log_safe


def test_log_safe_escapes_line_breaks_and_truncates_values() -> None:
    """Log safe escapes line breaks and truncates values."""
    assert log_safe("a\nERROR fake") == "a\\nERROR fake"
    assert log_safe("a\rERROR fake") == "a\\rERROR fake"
    assert log_safe("a\x00b") == "a?b"
    assert log_safe("abcdefgh", limit=5) == "abcde"
    assert log_safe(None) == ""
