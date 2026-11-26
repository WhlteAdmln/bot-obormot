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


def _markup_tokens_are_whole(chunk: str) -> bool:
    """Return whether the HTML tags and entities of a chunk are not fragmented."""
    without_tags = _TAG_PATTERN.sub("", chunk)
    without_entities = _ENTITY_PATTERN.sub("", without_tags)
    escaped_less_than = "<"
    escaped_greater_than = ">"
    escaped_ampersand = "&"
    return (
        escaped_less_than not in without_tags
        and escaped_greater_than not in without_tags
        and escaped_ampersand not in without_entities
    )


def _tags_are_balanced(chunk: str) -> bool:
    """Return whether a chunk contains independently balanced HTML tags."""
    stack: list[str] = []

    for match in _TAG_PATTERN.finditer(chunk):
        tag = match.group("name")
        if not match.group("closing"):
            stack.append(tag)
        elif not stack or stack.pop() != tag:
            return False

    expected_empty: list[str] = []
    return stack == expected_empty


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
def test_splitter_property_preserves_plain_unicode_text(
    text: str,
    max_length: int,
) -> None:
    chunks = split_formatted_message(text, max_length=max_length)

    assert "".join(chunks) == text, "the chunks do not join back into the text"


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
def test_splitter_property_respects_the_limit_for_plain_text(
    text: str,
    max_length: int,
) -> None:
    chunks = split_formatted_message(text, max_length=max_length)

    assert all(_utf16_length(chunk) <= max_length for chunk in chunks), (
        "a plain chunk exceeds the limit"
    )


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
def test_splitter_property_preserves_the_visible_text_of_markup(
    tag: str,
    text: str,
    max_length: int,
) -> None:
    formatted = f"<{tag}>{html.escape(text, quote=False)}</{tag}>"
    chunks = split_formatted_message(formatted, max_length=max_length)

    visible = "".join(_visible_text(chunk) for chunk in chunks)
    assert visible == _visible_text(formatted), "the visible text changed"


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
def test_splitter_property_respects_the_limit_for_visible_markup_text(
    tag: str,
    text: str,
    max_length: int,
) -> None:
    formatted = f"<{tag}>{html.escape(text, quote=False)}</{tag}>"
    chunks = split_formatted_message(formatted, max_length=max_length)

    assert all(_utf16_length(_visible_text(chunk)) <= max_length for chunk in chunks), (
        "the visible text of a chunk exceeds the limit"
    )


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
def test_splitter_property_keeps_tags_and_entities_whole(
    tag: str,
    text: str,
    max_length: int,
) -> None:
    formatted = f"<{tag}>{html.escape(text, quote=False)}</{tag}>"
    chunks = split_formatted_message(formatted, max_length=max_length)

    assert all(_markup_tokens_are_whole(chunk) for chunk in chunks), (
        "a tag or an entity is fragmented"
    )


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
def test_splitter_property_balances_tags_in_each_chunk(
    tag: str,
    text: str,
    max_length: int,
) -> None:
    formatted = f"<{tag}>{html.escape(text, quote=False)}</{tag}>"
    chunks = split_formatted_message(formatted, max_length=max_length)

    assert all(_tags_are_balanced(chunk) for chunk in chunks), (
        "a chunk has unbalanced tags"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("ж", ["ж"]),
        ("😀", ["😀"]),
    ],
)
def test_splitter_handles_empty_and_single_character_inputs(
    text: str,
    expected: list[str],
) -> None:
    max_length = 2
    chunks = split_formatted_message(text, max_length=max_length)
    assert chunks == expected, f"{text!r} is split wrongly"


def test_splitter_splits_very_long_single_word_into_several_chunks() -> None:
    text = "сверхдлинноеслово🚀" * 200
    max_length = 17

    chunks = split_formatted_message(text, max_length=max_length)

    assert len(chunks) > 1, "a very long word is not split"


def test_splitter_keeps_the_text_of_a_very_long_single_word() -> None:
    text = "длиннющеесловечко🛰" * 150
    max_length = 19

    chunks = split_formatted_message(text, max_length=max_length)

    assert "".join(chunks) == text, "the chunks of a long word lose text"


def test_splitter_respects_the_limit_for_a_very_long_single_word() -> None:
    text = "неперелазивый🚀слог" * 170
    max_length = 13

    chunks = split_formatted_message(text, max_length=max_length)

    assert all(_utf16_length(chunk) <= max_length for chunk in chunks), (
        "a chunk of a long word exceeds the limit"
    )


def test_splitter_keeps_unmatched_closing_tag_at_the_start() -> None:
    text = "</b>abc"
    max_length = 1
    closing_tag = "</b>"

    chunks = split_formatted_message(text, max_length=max_length)

    assert chunks[0].startswith(closing_tag), "the unmatched closing tag is broken"


def test_splitter_keeps_the_visible_text_after_an_unmatched_closing_tag() -> None:
    text = "</b>xyz"
    max_length = 1
    expected_text = "xyz"

    chunks = split_formatted_message(text, max_length=max_length)

    visible = "".join(_visible_text(chunk) for chunk in chunks)
    assert visible == expected_text, "the text after the closing tag changed"


def test_splitter_keeps_an_unmatched_closing_tag_whole() -> None:
    text = "</b>qrs"
    max_length = 1

    chunks = split_formatted_message(text, max_length=max_length)

    assert all(_markup_tokens_are_whole(chunk) for chunk in chunks), (
        "the unmatched closing tag is fragmented"
    )


def test_splitter_flushes_before_an_entity_that_exceeds_limit() -> None:
    text = "A&amp;"
    max_length = 1
    expected_chunks = ["A", "&amp;"]

    chunks = split_formatted_message(text, max_length=max_length)

    assert chunks == expected_chunks, "the text before the entity is not flushed"


def test_splitter_keeps_visible_text_within_the_limit_around_an_entity() -> None:
    text = "Z&gt;"
    max_length = 1

    chunks = split_formatted_message(text, max_length=max_length)

    assert all(_utf16_length(_visible_text(chunk)) <= max_length for chunk in chunks), (
        "a chunk around an entity exceeds the limit"
    )


def test_splitter_keeps_an_entity_that_exceeds_the_limit_whole() -> None:
    text = "Q&lt;"
    max_length = 1

    chunks = split_formatted_message(text, max_length=max_length)

    assert all(_markup_tokens_are_whole(chunk) for chunk in chunks), (
        "an entity is fragmented"
    )


def test_html_splitter_treats_a_lone_angle_bracket_as_text() -> None:
    text = "<b>a &lt; b</b>"
    max_length = 100
    expected_chunks = ["<b>a &lt; b</b>"]
    chunks = split_formatted_message(text, max_length=max_length)
    assert chunks == expected_chunks, "a lone angle bracket changed the split"


def test_splitter_closes_and_reopens_html_tags() -> None:
    text = "<b>abcd</b>"
    max_length = 2
    expected_chunks = ["<b>ab</b>", "<b>cd</b>"]
    chunks = split_formatted_message(text, max_length=max_length)
    assert chunks == expected_chunks, "the tags are not closed and reopened"


def test_splitter_preserves_entities_and_utf16_characters() -> None:
    text = "<b>A&amp;😀B</b>"
    max_length = 3
    expected_chunks = ["<b>A&amp;</b>", "<b>😀B</b>"]
    chunks = split_formatted_message(text, max_length=max_length)
    assert chunks == expected_chunks, "entities or UTF-16 characters are split"


def test_splitter_does_not_split_single_character_larger_than_limit() -> None:
    text = "😀"
    max_length = 1
    expected_chunks = ["😀"]
    chunks = split_formatted_message(text, max_length=max_length)
    assert chunks == expected_chunks, "a single wide character is split"


def test_splitter_rejects_non_positive_limit() -> None:
    text = "две\nстроки"
    max_length = 0
    expected_message = "max_length must be greater than zero."
    with pytest.raises(ValueError, match=re.escape(expected_message)) as excinfo:
        split_formatted_message(text, max_length=max_length)
    assert str(excinfo.value) == expected_message, "the limit error message differs"
