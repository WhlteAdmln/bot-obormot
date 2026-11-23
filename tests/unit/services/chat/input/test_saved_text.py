# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input saved text."""

from __future__ import annotations

from types import SimpleNamespace

from bot_obormot.services.chat.input import (
    MessageInfo,
)
from bot_obormot.services.chat.input import saved_text as history_module
from tests.support.message_input import make_message


def test_build_saved_user_text_preserves_media_descriptions_and_caption() -> None:
    """Build saved user text preserves media descriptions and caption."""
    info = MessageInfo(
        file_id="file-id",
        media_type="gif",
        audio_file_id=None,
        audio_filename=None,
        document=None,
        has_media=True,
        has_audio=False,
        has_document=False,
        has_text=False,
    )
    result = history_module.build_saved_user_text(
        make_message(text=None, caption="Подпись"),
        info,
        text_override=None,
        transcribed_text=None,
        document_format=None,
    )

    assert result == "[Пользователь отправил анимацию: gif] Подпись"


def test_build_saved_user_text_preserves_audio_caption() -> None:
    """Build saved user text preserves audio caption."""
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
    result = history_module.build_saved_user_text(
        make_message(text=None, caption="Контекст"),
        info,
        text_override=None,
        transcribed_text="Распознанная фраза",
        document_format=None,
    )

    assert result == "Контекст\n\n[Голосовое сообщение]: Распознанная фраза"


def test_build_saved_user_text_distinguishes_photo_from_other_media() -> None:
    """Build saved user text distinguishes photo from other media."""
    info = MessageInfo(
        file_id="photo-id",
        media_type="image",
        audio_file_id=None,
        audio_filename=None,
        document=None,
        has_media=True,
        has_audio=False,
        has_document=False,
        has_text=False,
    )
    result = history_module.build_saved_user_text(
        make_message(text=None, photo=[object()]),
        info,
        text_override=None,
        transcribed_text=None,
        document_format=None,
    )

    assert result == "[Пользователь отправил фотографию]"


def test_build_saved_user_text_preserves_document_format_label() -> None:
    """Build saved user text preserves document format label."""
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
    result = history_module.build_saved_user_text(
        make_message(text=None),
        info,
        text_override=None,
        transcribed_text=None,
        document_format="pdf",
    )

    assert result == "[Пользователь отправил документ: report.pdf (PDF)]"
