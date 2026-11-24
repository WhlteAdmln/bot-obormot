# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input saved text."""

from __future__ import annotations

from types import SimpleNamespace

from bot_obormot.services.chat.input import saved_text as history_module
from tests.support.message_input import make_info, make_message


def test_build_saved_user_text_preserves_media_descriptions_and_caption() -> None:
    info = make_info(file_id="file-id", media_type="gif", has_media=True)
    result = history_module.build_saved_user_text(
        make_message(text=None, caption="Подпись"),
        info,
        text_override=None,
        transcribed_text=None,
        document_format=None,
    )

    expected_result = "[Пользователь отправил анимацию: gif] Подпись"
    assert result == expected_result


def test_build_saved_user_text_preserves_audio_caption() -> None:
    info = make_info(
        audio_file_id="voice-id", audio_filename="voice.ogg", has_audio=True
    )
    result = history_module.build_saved_user_text(
        make_message(text=None, caption="Контекст"),
        info,
        text_override=None,
        transcribed_text="Распознанная фраза",
        document_format=None,
    )

    expected_result = "Контекст\n\n[Голосовое сообщение]: Распознанная фраза"
    assert result == expected_result


def test_build_saved_user_text_distinguishes_photo_from_other_media() -> None:
    info = make_info(file_id="photo-id", media_type="image", has_media=True)
    result = history_module.build_saved_user_text(
        make_message(text=None, photo=[object()]),
        info,
        text_override=None,
        transcribed_text=None,
        document_format=None,
    )

    expected_result = "[Пользователь отправил фотографию]"
    assert result == expected_result


def test_build_saved_user_text_preserves_document_format_label() -> None:
    document = SimpleNamespace(file_name="report.pdf")
    info = make_info(document=document, has_document=True)
    result = history_module.build_saved_user_text(
        make_message(text=None),
        info,
        text_override=None,
        transcribed_text=None,
        document_format="pdf",
    )

    expected_result = "[Пользователь отправил документ: report.pdf (PDF)]"
    assert result == expected_result
