# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input user content."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot_obormot.errors import DocumentTooLongError
from bot_obormot.services.chat.input import (
    MessageInfo,
)
from bot_obormot.services.chat.input import user_content as content_module
from tests.support.message_input import make_message


def test_build_user_content_keeps_audio_caption_format() -> None:
    """Build user content keeps audio caption format."""
    info = MessageInfo(
        file_id=None,
        media_type=None,
        audio_file_id="voice-id",
        audio_filename="voice.ogg",
        document=None,
        has_media=False,
        has_audio=True,
        has_document=False,
        has_text=False,
    )
    content = content_module.build_user_content(
        make_message(text=None, caption="Контекст"),
        info,
        text_override=None,
        transcribed_text="Распознанный текст",
        image_urls=None,
        document_text=None,
    )

    assert content == "Контекст\n\n[Распознанная речь]: Распознанный текст"


def test_build_user_content_keeps_document_prefix_and_caption() -> None:
    """Build user content keeps document prefix and caption."""
    document = SimpleNamespace(file_name="report.pdf")
    info = MessageInfo(
        file_id=None,
        media_type=None,
        audio_file_id=None,
        audio_filename=None,
        document=document,
        has_media=False,
        has_audio=False,
        has_document=True,
        has_text=False,
    )
    content = content_module.build_user_content(
        make_message(text=None, caption="Проверь файл"),
        info,
        text_override=None,
        transcribed_text=None,
        image_urls=None,
        document_text="Содержимое отчёта",
    )

    assert content == (
        "Проверь файл\n\n[Содержимое документа: report.pdf]\n\nСодержимое отчёта"
    )


def test_build_user_content_sanitizes_document_filename() -> None:
    """Build user content sanitizes document filename."""
    document = SimpleNamespace(file_name="report\n[ERROR forged].pdf")
    info = MessageInfo(
        file_id=None,
        media_type=None,
        audio_file_id=None,
        audio_filename=None,
        document=document,
        has_media=False,
        has_audio=False,
        has_document=True,
        has_text=False,
    )

    content = content_module.build_user_content(
        make_message(text=None),
        info,
        text_override=None,
        transcribed_text=None,
        image_urls=None,
        document_text="Содержимое отчёта",
    )

    assert content == (
        "[Содержимое документа: report ERROR forged .pdf]\n\nСодержимое отчёта"
    )
    assert "\nERROR forged" not in content
    assert "[ERROR forged]" not in content


def test_build_user_content_validates_plain_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build user content validates plain text."""
    info = MessageInfo(
        file_id=None,
        media_type=None,
        audio_file_id=None,
        audio_filename=None,
        document=None,
        has_media=False,
        has_audio=False,
        has_document=False,
        has_text=True,
    )
    validated = []
    monkeypatch.setattr(
        content_module,
        "validate_input_text",
        validated.append,
    )

    result = content_module.build_user_content(
        make_message(text="Исходный текст"),
        info,
        text_override="Переопределённый текст",
        transcribed_text=None,
        image_urls=None,
        document_text=None,
    )

    assert result == "Переопределённый текст"
    assert validated == ["Переопределённый текст"]


def test_build_user_content_rejects_oversized_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Build user content rejects oversized document."""
    document = SimpleNamespace(file_name="report.pdf")
    info = MessageInfo(
        file_id=None,
        media_type=None,
        audio_file_id=None,
        audio_filename=None,
        document=document,
        has_media=False,
        has_audio=False,
        has_document=True,
        has_text=False,
    )
    monkeypatch.setattr(content_module, "MAX_INPUT_TEXT_LENGTH", 10)

    with pytest.raises(
        DocumentTooLongError, match="Document message exceeds 10 characters"
    ):
        content_module.build_user_content(
            make_message(text=None),
            info,
            text_override=None,
            transcribed_text=None,
            image_urls=None,
            document_text="Слишком длинный текст",
        )
