# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media content."""

from types import SimpleNamespace

import pytest

from bot_obormot.services import media
from bot_obormot.services.media import content as media_content
from tests.support.media import make_message


def test_get_user_content_describes_animation_contact_sheet() -> None:
    """Get user content describes animation contact sheet."""
    message = make_message(caption=None, sticker=None, text="ignored")
    content = media.get_user_content(
        message,
        ["data:image/jpeg;base64,combined"],
        "tgs",
    )

    assert len(content) == 2
    assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,combined"
    assert "одно нумерованное изображение-монтаж" in content[0]["text"]
    assert "сверху вниз" in content[0]["text"]


@pytest.mark.parametrize(
    ("image_urls", "media_type", "expected_fragment"),
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
        (
            ["data:image/jpeg;base64,AA=="],
            "image",
            None,
        ),
    ],
)
def test_get_user_content_formats_media_prompts(
    monkeypatch: pytest.MonkeyPatch,
    image_urls: list[str],
    media_type: str,
    expected_fragment: str | None,
) -> None:
    """Add animation guidance only for animations or multiple frames."""
    monkeypatch.setattr(
        media_content,
        "get_media_prompt",
        lambda _message, _media_type: "Prompt",
    )

    result = media_content.get_user_content(
        SimpleNamespace(text="plain text"),
        image_urls,
        media_type,
    )

    assert isinstance(result, list)
    assert result[0]["text"].startswith("Prompt")
    assert [part["image_url"]["url"] for part in result[1:]] == image_urls
    if expected_fragment is not None:
        assert expected_fragment in result[0]["text"]
    else:
        assert result[0]["text"] == "Prompt"


@pytest.mark.parametrize("image_urls", [None, []])
def test_get_user_content_returns_plain_text_without_images(
    image_urls: list[str] | None,
) -> None:
    """Return the original message text when there are no images."""
    message = SimpleNamespace(text="plain text")

    assert media_content.get_user_content(message, image_urls, "image") == "plain text"
