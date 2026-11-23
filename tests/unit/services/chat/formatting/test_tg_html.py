# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting tg html."""

from bot_obormot.services.chat.formatting import (
    sanitize_html,
)


def test_sanitize_html_keeps_supported_tags_and_escapes_the_rest() -> None:
    """Keep whitelisted tags and attributes; escape everything else."""
    text = (
        '<b>x</b> a<br>b & <a href="javascript:x">l</a> '
        '<a href="https://e.com?a=1&b=2">ok</a> '
        '<code class="language-py">c</code> <span>n</span> 1<2'
    )

    expected_sanitize_html = (
        "<b>x</b> a\nb &amp; l "
        '<a href="https://e.com?a=1&amp;b=2">ok</a> '
        '<code class="language-py">c</code> n 1&lt;2'
    )
    assert sanitize_html(text) == expected_sanitize_html
