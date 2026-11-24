# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for inline MarkdownV2 rendering."""

from bot_obormot.services.chat.formatting.markdown_v2.inline import render_inline


def test_renders_link_label_with_emphasis() -> None:
    text = "[**важно** тут](https://docs.example.net/a)"
    expected = "[*важно* тут](https://docs.example.net/a)"

    assert render_inline(text) == expected, "link label lost its emphasis"


def test_shows_escaped_url_for_link_without_label() -> None:
    text = "[](https://x.example.io/v1.2)"
    expected = "[https://x\\.example\\.io/v1\\.2](https://x.example.io/v1.2)"

    assert render_inline(text) == expected, "empty label must show the URL"


def test_shows_image_word_for_image_without_alt_text() -> None:
    text = "![](https://cdn.example.com/cat.png)"
    expected = "[image](https://cdn.example.com/cat.png)"

    assert render_inline(text) == expected, "image without alt text is wrong"


def test_keeps_markup_inside_active_kind_unwrapped() -> None:
    text = "**уже жирный**"
    active = frozenset({"bold"})
    expected = "уже жирный"

    assert render_inline(text, active) == expected, "nested bold was wrapped"
