# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for message preparation."""

from __future__ import annotations

import base64
import inspect
import logging
from types import SimpleNamespace

import pytest

from bot.errors import DocumentAPIError, DocumentTooLongError
from bot.services.chat import input as chat_input
from bot.services.chat.input import (
    MessageInfo,
    PreparedMessage,
    inspect_message,
    prepare_message,
)
from bot.services.chat.input import audio_part as audio_module
from bot.services.chat.input import document_part as documents_module
from bot.services.chat.input import inspection as inspection_module
from bot.services.chat.input import media_part as media_module
from bot.services.chat.input import prepare as pipeline_module
from bot.services.chat.input import saved_text as history_module
from bot.services.chat.input import user_content as content_module


def make_message(**overrides: object) -> SimpleNamespace:
    """Make message."""
    values = {
        "text": "Привет",
        "caption": None,
        "document": None,
        "photo": None,
        "sticker": None,
        "voice": None,
        "audio": None,
        "video_note": None,
        "animation": None,
        "video": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def no_media(_message: object) -> tuple[object, ...]:
    """No media."""
    return None, None


def no_audio(_message: object) -> tuple[object, ...]:
    """No audio."""
    return None, None


def test_new_chat_input_package_reexports_the_public_api() -> None:
    """New chat input package reexports the public api."""
    assert chat_input.MessageInfo is MessageInfo
    assert chat_input.PreparedMessage is PreparedMessage
    assert chat_input.inspect_message.__name__ == "inspect_message"
    assert chat_input.prepare_message.__name__ == "prepare_message"


def test_public_api_keeps_original_function_signatures() -> None:
    """Public api keeps original function signatures."""
    assert list(inspect.signature(inspect_message).parameters) == ["message"]
    assert list(inspect.signature(prepare_message).parameters) == [
        "message",
        "info",
        "text_override",
    ]


def test_inspect_message_marks_plain_text_and_ignores_commands() -> None:
    """Inspect message marks plain text and ignores commands."""
    message = make_message(text="Привет")
    info = inspection_module.inspect_message(
        message,
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )

    assert info.has_text is True
    assert info.has_content is True
    assert info.has_media is False
    assert info.has_audio is False
    assert info.has_document is False

    command = make_message(text="/start")
    command_info = inspection_module.inspect_message(
        command,
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )
    assert command_info.has_text is False
    assert command_info.has_content is False


def test_inspect_message_routes_image_documents_to_media() -> None:
    """Inspect message routes image documents to media."""
    document = SimpleNamespace(
        file_id="document-image-id",
        file_name="picture.bin",
        mime_type="image/png",
    )
    info = inspection_module.inspect_message(
        make_message(document=document, text=None),
        media_info_getter=no_media,
        audio_info_getter=no_audio,
    )

    assert info.file_id == "document-image-id"
    assert info.media_type == "image"
    assert info.has_media is True
    assert info.has_document is False


def test_inspect_message_keeps_non_image_documents_as_documents() -> None:
    """Inspect message keeps non image documents as documents."""
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

    assert info.file_id is None
    assert info.has_media is False
    assert info.has_document is True


def test_message_info_has_content_is_true_for_each_supported_kind() -> None:
    """Message info has content is true for each supported kind."""
    base = {
        "file_id": None,
        "media_type": None,
        "audio_file_id": None,
        "audio_filename": None,
        "document": None,
        "has_media": False,
        "has_audio": False,
        "has_document": False,
        "has_text": False,
    }
    assert MessageInfo(**base).has_content is False
    for field in ("has_media", "has_audio", "has_document", "has_text"):
        assert MessageInfo(**(base | {field: True})).has_content is True


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


@pytest.mark.asyncio
async def test_prepare_audio_preserves_validation_download_and_transcription_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prepare audio preserves validation download and transcription order."""
    events = []
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

    def validate(_message: object) -> None:
        events.append("validate")

    async def download(_message: object, file_id: str) -> bytes:
        events.append(("download", file_id))
        return b"audio-bytes"

    async def transcribe(data: object, filename: object) -> str:
        events.append(("transcribe", data, filename))
        return "Распознано"

    with caplog.at_level(logging.INFO, logger=audio_module.logger.name):
        result = await audio_module.prepare_audio(
            make_message(),
            info,
            duration_validator=validate,
            downloader=download,
            transcriber=transcribe,
        )

    assert result == "Распознано"
    assert "Распознано" not in caplog.text
    assert "AUDIO: распознано символов: 10" in caplog.text
    assert "Recognized audio text" not in caplog.text
    assert events == [
        "validate",
        ("download", "voice-id"),
        ("transcribe", b"audio-bytes", "voice.ogg"),
    ]


@pytest.mark.asyncio
async def test_prepare_media_decodes_data_urls_to_original_image_bytes() -> None:
    """Prepare media decodes data urls to original image bytes."""
    image = b"image-data"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")

    async def process(_message: object, media_type: str, file_id: str) -> list[object]:
        assert (media_type, file_id) == ("image", "image-id")
        return [data_url]

    info = MessageInfo(
        file_id="image-id",
        media_type="image",
        audio_file_id=None,
        audio_filename=None,
        document=None,
        has_media=True,
        has_audio=False,
        has_document=False,
        has_text=False,
    )
    urls, image_bytes = await media_module.prepare_media(
        make_message(),
        info,
        media_processor=process,
    )

    assert urls == [data_url]
    assert image_bytes == [image]


@pytest.mark.asyncio
async def test_prepare_document_rejects_empty_extracted_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prepare document rejects empty extracted text."""
    filename = "empty.pdf\nERROR forged entry"
    document = SimpleNamespace(file_id="doc-id", file_name=filename)
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

    async def download(_message: object, file_id: str) -> bytes:
        assert file_id == "doc-id"
        return b"document-bytes"

    async def process(_data: object, actual_filename: object) -> dict[str, object]:
        # Очистка относится только к логам, а не к имени файла для сервиса.
        assert actual_filename == filename
        return {"text": "  ", "format": "pdf", "characters": 0}

    with (
        caplog.at_level(logging.INFO, logger=documents_module.logger.name),
        pytest.raises(
            DocumentAPIError,
            match="Document contains no extractable text",
        ),
    ):
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
        )

    assert r"DOCUMENT: начинаю скачивание: empty.pdf\nERROR forged entry" in caplog.text
    assert "\nERROR forged entry" not in caplog.text


@pytest.mark.asyncio
async def test_prepare_document_rejects_truncated_extracted_text() -> None:
    """Prepare document rejects truncated extracted text."""
    document = SimpleNamespace(file_id="doc-id", file_name="large.pdf")
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

    async def download(_message: object, _file_id: object) -> bytes:
        return b"document-bytes"

    async def process(_data: object, _filename: object) -> dict[str, object]:
        return {
            "text": "Извлечённый фрагмент",
            "format": "pdf",
            "characters": 20,
            "truncated": True,
        }

    with pytest.raises(DocumentTooLongError):
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
        )


@pytest.mark.asyncio
async def test_prepare_message_preserves_processing_order_and_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prepare message preserves processing order and result."""
    events = []
    info = MessageInfo(
        file_id="image-id",
        media_type="image",
        audio_file_id="voice-id",
        audio_filename="voice.ogg",
        document=SimpleNamespace(file_id="doc-id", file_name="report.pdf"),
        has_media=True,
        has_audio=True,
        has_document=True,
        has_text=False,
    )
    image_bytes = [b"image-bytes"]

    async def prepare_audio(_message: object, _info: object) -> str:
        events.append("audio")
        return "Распознано"

    async def prepare_media(_message: object, _info: object) -> tuple[object, ...]:
        events.append("media")
        return ["data:image/jpeg;base64,AA=="], image_bytes

    async def prepare_document(_message: object, _info: object) -> tuple[object, ...]:
        events.append("document")
        return "Текст документа", "pdf"

    def build_content(_message: object, _info: object, **kwargs: object) -> str:
        events.append("content")
        assert kwargs["transcribed_text"] == "Распознано"
        assert kwargs["image_urls"] == ["data:image/jpeg;base64,AA=="]
        assert kwargs["document_text"] == "Текст документа"
        assert "document_format" not in kwargs
        return "Содержимое для LLM"

    def build_history(_message: object, _info: object, **kwargs: object) -> str:
        events.append("history")
        assert kwargs["document_format"] == "pdf"
        return "Текст для истории"

    monkeypatch.setattr(pipeline_module, "prepare_audio", prepare_audio)
    monkeypatch.setattr(pipeline_module, "prepare_media", prepare_media)
    monkeypatch.setattr(pipeline_module, "prepare_document", prepare_document)
    monkeypatch.setattr(pipeline_module, "build_user_content", build_content)
    monkeypatch.setattr(pipeline_module, "build_saved_user_text", build_history)

    result = await prepare_message(make_message(), info, text_override=None)

    assert events == ["audio", "media", "document", "content", "history"]
    assert result == PreparedMessage(
        user_content="Содержимое для LLM",
        saved_user_text="Текст для истории",
        image_bytes=image_bytes,
    )
