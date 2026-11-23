# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for formatting splitter."""

import html
import re

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from bot_obormot.services.chat.formatting import (
    split_formatted_message,
)

_TAG_PATTERN = re.compile(r"<(?P<closing>/)?(?P<name>b|i|blockquote)>")


_ENTITY_PATTERN = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]+);")


def _utf16_length(text: str) -> int:
    """Return the number of UTF-16 code units in text."""
    return len(text.encode("utf-16-le")) // 2


def _visible_text(chunk: str) -> str:
    """Return visible text after removing formatting tags and decoding entities."""
    return html.unescape(_TAG_PATTERN.sub("", chunk))


def _assert_markup_tokens_are_whole(chunk: str) -> None:
    """Assert that HTML tags and entities are not fragmented."""
    without_tags = _TAG_PATTERN.sub("", chunk)
    expected_fragment = "<"
    assert expected_fragment not in without_tags
    expected_fragment = ">"
    assert expected_fragment not in without_tags
    without_entities = _ENTITY_PATTERN.sub("", without_tags)
    expected_fragment = "&"
    assert expected_fragment not in without_entities


def _assert_tags_are_balanced(chunk: str) -> None:
    """Assert that each chunk contains independently balanced HTML tags."""
    stack: list[str] = []

    for match in _TAG_PATTERN.finditer(chunk):
        tag = match.group("name")
        assert tag is not None

        if match.group("closing"):
            assert stack
            assert stack.pop() == tag
        else:
            stack.append(tag)

    expected_empty = []
    assert stack == expected_empty, "expected an empty list"


@settings(max_examples=200, deadline=None)
@given(
    text=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters="<&",
        ),
        max_size=200,
    ),
    max_length=st.integers(min_value=2, max_value=32),
)
def test_splitter_property_preserves_plain_unicode_text_and_respects_limit(
    text: str,
    max_length: int,
) -> None:
    """Splitting plain Unicode text preserves it and respects the UTF-16 limit."""
    chunks = split_formatted_message(text, max_length=max_length)

    assert "".join(chunks) == text
    assert all(_utf16_length(chunk) <= max_length for chunk in chunks)


@settings(max_examples=200, deadline=None)
@given(
    tag=st.sampled_from(("i", "b", "blockquote")),
    text=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cs",),
            blacklist_characters="",
        ),
        min_size=1,
        max_size=160,
    ),
    max_length=st.integers(min_value=2, max_value=32),
)
def test_splitter_property_preserves_markup_and_entities(
    tag: str,
    text: str,
    max_length: int,
) -> None:
    """Splitting Telegram HTML preserves visible text and complete markup tokens."""
    formatted = f"<{tag}>{html.escape(text, quote=False)}</{tag}>"
    chunks = split_formatted_message(formatted, max_length=max_length)

    assert "".join(_visible_text(chunk) for chunk in chunks) == _visible_text(formatted)

    for chunk in chunks:
        assert _utf16_length(_visible_text(chunk)) <= max_length
        _assert_markup_tokens_are_whole(chunk)
        _assert_tags_are_balanced(chunk)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("x", ["x"]),
        ("😀", ["😀"]),
    ],
)
def test_splitter_handles_empty_and_single_character_inputs(
    text: str,
    expected: list[str],
) -> None:
    """Splitter handles empty input and single Unicode characters."""
    assert split_formatted_message(text, max_length=2) == expected


def test_splitter_splits_very_long_single_word() -> None:
    """Splitter respects the limit when the input contains one long word."""
    text = "сверхдлинноеслово🚀" * 200
    max_length = 17

    chunks = split_formatted_message(text, max_length=max_length)

    assert len(chunks) > 1
    assert "".join(chunks) == text
    assert all(_utf16_length(chunk) <= max_length for chunk in chunks)


def test_splitter_keeps_unmatched_closing_tag_atomic() -> None:
    """Splitter keeps an unmatched closing tag intact."""
    chunks = split_formatted_message("</b>abc", max_length=1)

    assert chunks[0].startswith("</b>")
    expected_text = "abc"
    assert "".join(_visible_text(chunk) for chunk in chunks) == expected_text
    for chunk in chunks:
        _assert_markup_tokens_are_whole(chunk)


def test_splitter_flushes_before_an_entity_that_exceeds_limit() -> None:
    """Splitter moves an entity to the next chunk when it exceeds the limit."""
    chunks = split_formatted_message("A&amp;", max_length=1)

    assert chunks == ["A", "&amp;"]
    assert all(_utf16_length(_visible_text(chunk)) <= 1 for chunk in chunks)
    for chunk in chunks:
        _assert_markup_tokens_are_whole(chunk)


def test_html_splitter_treats_a_lone_angle_bracket_as_text() -> None:
    """Do not fail on a bare "<" inside Telegram HTML."""
    assert split_formatted_message("<b>a < b</b>", max_length=100) == ["<b>a < b</b>"]


def test_splitter_closes_and_reopens_html_tags() -> None:
    """Splitter closes and reopens html tags."""
    assert split_formatted_message("<b>abcd</b>", max_length=2) == [
        "<b>ab</b>",
        "<b>cd</b>",
    ]


def test_splitter_preserves_entities_and_utf16_characters() -> None:
    """Splitter preserves entities and utf16 characters."""
    assert split_formatted_message("<b>A&amp;😀B</b>", max_length=3) == [
        "<b>A&amp;</b>",
        "<b>😀B</b>",
    ]


def test_splitter_does_not_split_single_character_larger_than_limit() -> None:
    """Splitter does not split single character larger than limit."""
    assert split_formatted_message("😀", max_length=1) == ["😀"]


def test_splitter_rejects_non_positive_limit() -> None:
    """Splitter rejects non positive limit."""
    with pytest.raises(ValueError, match=r"^max_length must be greater than zero\.$"):
        split_formatted_message("text", max_length=0)
