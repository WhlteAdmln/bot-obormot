# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media content."""

from types import SimpleNamespace
from typing import Any

import pytest

from bot_obormot.services import media
from bot_obormot.services.media import content as media_content
from tests.support.media import make_message


def _prompt_content(
    monkeypatch: pytest.MonkeyPatch, image_urls: list[str], media_type: str
) -> str | list[dict[str, Any]] | None:
    """Build user content with a fixed media prompt."""
    monkeypatch.setattr(
        media_content,
        "get_media_prompt",
        lambda _message, _media_type: "Prompt",
    )
    return media_content.get_user_content(
        SimpleNamespace(text="plain text"),
        image_urls,
        media_type,
    )


def test_get_user_content_adds_one_part_for_the_contact_sheet() -> None:
    message = make_message(caption=None, sticker=None, text="ignored")
    content = media.get_user_content(
        message,
        ["data:image/jpeg;base64,combined"],
        "tgs",
    )
    expected_count = 2
    assert len(content) == expected_count, "wrong number of content parts"


def test_get_user_content_passes_the_contact_sheet_url() -> None:
    message = make_message(caption=None, sticker=None, text="skipped")
    expected_url = "data:image/jpeg;base64,montage"
    content = media.get_user_content(message, [expected_url], "tgs")
    assert content[1]["image_url"]["url"] == expected_url, "wrong image URL"


@pytest.mark.parametrize(
    "expected_hint",
    ["одно нумерованное изображение-монтаж", "сверху вниз"],
)
def test_get_user_content_describes_animation_contact_sheet(
    expected_hint: str,
) -> None:
    message = make_message(caption=None, sticker=None, text="unused")
    content = media.get_user_content(
        message,
        ["data:image/jpeg;base64,sheet"],
        "tgs",
    )
    assert expected_hint in content[0]["text"], "the contact sheet hint is missing"


@pytest.mark.parametrize(
    ("image_urls", "media_type"),
    [
        (["data:image/jpeg;base64,AA=="], "tgs"),
        (["data:image/jpeg;base64,AA==", "data:image/jpeg;base64,AQ=="], "image"),
        (["data:image/jpeg;base64,AA=="], "image"),
    ],
)
def test_get_user_content_returns_a_list_for_media(
    monkeypatch: pytest.MonkeyPatch,
    image_urls: list[str],
    media_type: str,
) -> None:
    result = _prompt_content(monkeypatch, image_urls, media_type)
    assert isinstance(result, list), "media content is not a list"


@pytest.mark.parametrize(
    ("image_urls", "media_type"),
    [
        (["data:image/jpeg;base64,AB=="], "tgs"),
        (["data:image/jpeg;base64,AB==", "data:image/jpeg;base64,AC=="], "image"),
        (["data:image/jpeg;base64,AB=="], "image"),
    ],
)
def test_get_user_content_starts_with_the_media_prompt(
    monkeypatch: pytest.MonkeyPatch,
    image_urls: list[str],
    media_type: str,
) -> None:
    result = _prompt_content(monkeypatch, image_urls, media_type)
    expected_prefix = "Prompt"
    assert result[0]["text"].startswith(expected_prefix), "the prompt is missing"


@pytest.mark.parametrize(
    ("image_urls", "media_type"),
    [
        (["data:image/jpeg;base64,AD=="], "tgs"),
        (["data:image/jpeg;base64,AD==", "data:image/jpeg;base64,AE=="], "image"),
        (["data:image/jpeg;base64,AD=="], "image"),
    ],
)
def test_get_user_content_keeps_the_image_urls(
    monkeypatch: pytest.MonkeyPatch,
    image_urls: list[str],
    media_type: str,
) -> None:
    result = _prompt_content(monkeypatch, image_urls, media_type)
    urls = [part["image_url"]["url"] for part in result[1:]]
    assert urls == image_urls, "the image URLs differ"


@pytest.mark.parametrize(
    ("image_urls", "media_type", "expected_hint"),
    [
        (
            ["data:image/jpeg;base64,AA=="],
            "tgs",
            "одно нумерованное изображение-монтаж",
        ),
        (
            [
                "data:image/jpeg;base64,AA==",
                "data:image/jpeg;base64,AQ==",
            ],
            "image",
            "Кадры расположены в хронологическом порядке",
        ),
    ],
)
def test_get_user_content_formats_media_prompts(
    monkeypatch: pytest.MonkeyPatch,
    image_urls: list[str],
    media_type: str,
    expected_hint: str,
) -> None:
    result = _prompt_content(monkeypatch, image_urls, media_type)
    assert expected_hint in result[0]["text"], "the media hint is missing"


def test_get_user_content_keeps_the_prompt_alone_for_one_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_urls = ["data:image/jpeg;base64,AF=="]
    result = _prompt_content(monkeypatch, image_urls, "image")
    expected_text = "Prompt"
    assert result[0]["text"] == expected_text, "a single image got a hint"


@pytest.mark.parametrize("image_urls", [None, []])
def test_get_user_content_returns_plain_text_without_images(
    image_urls: list[str] | None,
) -> None:
    message = SimpleNamespace(text="plain text")

    expected_get_user_content = "plain text"
    assert (
        media_content.get_user_content(message, image_urls, "image")
        == expected_get_user_content
    ), "plain text was not returned as is"
