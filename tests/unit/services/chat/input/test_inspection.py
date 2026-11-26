# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input inspection."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot_obormot.services.chat.input import inspection as inspection_module
from tests.support.message_input import make_message


def no_media(_message: object) -> tuple[object, ...]:
    """No media."""
    return None, None


def no_audio(_message: object) -> tuple[object, ...]:
    """No audio."""
    return None, None


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("has_text", True),
        ("has_content", True),
        ("has_media", False),
        ("has_audio", False),
        ("has_document", False),
    ],
)
def test_inspect_message_marks_plain_text(attribute: str, expected: object) -> None:
    text = "Привет, как дела?"
    info = inspection_module.inspect_message(
        make_message(text=text),
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )
    assert getattr(info, attribute) is expected, f"plain text has a wrong {attribute}"


@pytest.mark.parametrize("attribute", ["has_text", "has_content"])
def test_inspect_message_ignores_commands(attribute: str) -> None:
    text = "/start"
    info = inspection_module.inspect_message(
        make_message(text=text),
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )
    assert getattr(info, attribute) is False, f"a command counts as {attribute}"


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("file_id", "document-image-id"),
        ("media_type", "image"),
        ("has_media", True),
        ("has_document", False),
    ],
)
def test_inspect_message_routes_image_documents_to_media(
    attribute: str, expected: object
) -> None:
    file_id = "document-image-id"
    document = SimpleNamespace(
        file_id=file_id,
        file_name="picture.bin",
        mime_type="image/png",
    )
    info = inspection_module.inspect_message(
        make_message(document=document, text=None),
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )
    assert getattr(info, attribute) == expected, (
        f"an image document has a wrong {attribute}"
    )


@pytest.mark.parametrize(
    ("attribute", "expected"),
    [
        ("file_id", None),
        ("has_media", False),
        ("has_document", True),
    ],
)
def test_inspect_message_keeps_non_image_documents_as_documents(
    attribute: str, expected: object
) -> None:
    document = SimpleNamespace(
        file_id="document-id",
        file_name="report.pdf",
        mime_type="application/pdf",
    )
    info = inspection_module.inspect_message(
        make_message(document=document, text=None),
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )
    assert getattr(info, attribute) == expected, (
        f"a non-image document has a wrong {attribute}"
    )
