# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input user content."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from bot_obormot.errors import DocumentTooLongError
from bot_obormot.services.chat.input import user_content as content_module
from tests.support.message_input import make_info, make_message


def test_build_user_content_keeps_audio_caption_format() -> None:
    info = make_info(
        audio_file_id="voice-id", audio_filename="voice.ogg", has_audio=True
    )
    content = content_module.build_user_content(
        make_message(text=None, caption="Контекст"),
        info,
        text_override=None,
        transcribed_text="Распознанный текст",
        image_urls=None,
        document_text=None,
    )

    expected_content = "Контекст\n\n[Распознанная речь]: Распознанный текст"
    assert content == expected_content, "the audio caption format changed"


def test_build_user_content_keeps_document_prefix_and_caption() -> None:
    document = SimpleNamespace(file_name="report.pdf")
    info = make_info(document=document, has_document=True)
    content = content_module.build_user_content(
        make_message(text=None, caption="Проверь файл"),
        info,
        text_override=None,
        transcribed_text=None,
        image_urls=None,
        document_text="Содержимое отчёта",
    )

    expected_content = (
        "Проверь файл\n\n[Содержимое документа: report.pdf]\n\nСодержимое отчёта"
    )
    assert content == expected_content, "the document prefix or caption changed"


def _document_content(file_name: str, document_text: str) -> str:
    document = SimpleNamespace(file_name=file_name)
    info = make_info(document=document, has_document=True)
    content = content_module.build_user_content(
        make_message(text=None),
        info,
        text_override=None,
        transcribed_text=None,
        image_urls=None,
        document_text=document_text,
    )
    return str(content)


def test_build_user_content_sanitizes_document_filename() -> None:
    content = _document_content("report\n[ERROR forged].pdf", "Содержимое отчёта")

    expected_content = (
        "[Содержимое документа: report ERROR forged .pdf]\n\nСодержимое отчёта"
    )
    assert content == expected_content, "the document filename was not sanitized"


def test_build_user_content_drops_newlines_from_document_filename() -> None:
    content = _document_content("scan\nERROR forged.docx", "Страница один")

    forged_line = "\nERROR forged"
    assert forged_line not in content, "the filename injected a new line"


def test_build_user_content_drops_brackets_from_document_filename() -> None:
    content = _document_content("notes[ERROR forged].txt", "Заметки")

    escaped_forged_line = "[ERROR forged]"
    assert escaped_forged_line not in content, "the filename injected a marker"


@pytest.fixture(name="validated")
def fixture_validated(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the texts passed to validation instead of validating them."""
    validated: list[str] = []
    monkeypatch.setattr(content_module, "validate_input_text", validated.append)
    return validated


@pytest.mark.usefixtures("validated")
def test_build_user_content_returns_the_text_override() -> None:
    override = "Переопределённый текст"

    result = content_module.build_user_content(
        make_message(text="Исходный текст"),
        make_info(has_text=True),
        text_override=override,
        transcribed_text=None,
        image_urls=None,
        document_text=None,
    )

    assert result == override, "the text override was not returned"


def test_build_user_content_validates_plain_text(validated: list[str]) -> None:
    override = "Уточнённый вопрос"

    content_module.build_user_content(
        make_message(text="Первый вопрос"),
        make_info(has_text=True),
        text_override=override,
        transcribed_text=None,
        image_urls=None,
        document_text=None,
    )

    expected = [override]
    assert validated == expected, "the plain text was not validated"


def test_build_user_content_rejects_oversized_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = SimpleNamespace(file_name="report.pdf")
    info = make_info(document=document, has_document=True)
    monkeypatch.setattr(content_module, "MAX_INPUT_TEXT_LENGTH", 10)

    with pytest.raises(
        DocumentTooLongError, match="Document message exceeds 10 characters"
    ) as excinfo:
        content_module.build_user_content(
            make_message(text=None),
            info,
            text_override=None,
            transcribed_text=None,
            image_urls=None,
            document_text="Слишком длинный текст",
        )

    assert excinfo.type is DocumentTooLongError, "the oversized document passed"
