# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for Markdown block parsing."""

from bot_obormot.services.chat.formatting.markdown_v2.blocks import next_block


def test_renders_heading_and_returns_next_line_index() -> None:
    lines = ["## План на 2027", "текст"]
    expected = ("*План на 2027*", 1)

    assert next_block(lines, 0) == expected, "heading block is wrong"


def test_renders_task_list_items_with_check_marks() -> None:
    lines = ["- [x] сделано", "- [ ] осталось"]
    expected = ("☑ сделано\n☐ осталось", 2)

    assert next_block(lines, 0) == expected, "task list is wrong"


def test_stops_paragraph_before_quote() -> None:
    lines = ["первая строка", "вторая", "> цитата"]
    expected = ("первая строка\nвторая", 2)

    assert next_block(lines, 0) == expected, "paragraph swallowed the quote"
