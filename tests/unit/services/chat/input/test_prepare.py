# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input prepare."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from bot_obormot.services.chat.input import (
    MessageInfo,
    PreparedMessage,
    prepare_message,
)
from bot_obormot.services.chat.input import prepare as pipeline_module
from bot_obormot.services.media.slots import MediaSlots
from tests.support.message_input import make_info, make_message
from tests.support.settings import make_settings

if TYPE_CHECKING:
    from bot_obormot.settings import Settings

Calls = dict[str, dict[str, object]]
Install = Callable[[Mapping[str, object]], Calls]


async def _download(_message: object, _file_id: str) -> bytes:
    return b"never-downloaded"


def _full_info(document_name: str) -> MessageInfo:
    return make_info(
        file_id="image-id",
        media_type="image",
        audio_file_id="voice-id",
        audio_filename="voice.ogg",
        document=SimpleNamespace(file_id="doc-id", file_name=document_name),
        has_media=True,
        has_audio=True,
        has_document=True,
    )


async def _prepare(
    info: MessageInfo, settings: Settings, media_slots: MediaSlots
) -> PreparedMessage:
    return await prepare_message(
        make_message(),
        info,
        text_override=None,
        settings=settings,
        downloader=_download,
        media_slots=media_slots,
    )


@pytest.fixture(name="install_pipeline")
def fixture_install_pipeline(monkeypatch: pytest.MonkeyPatch) -> Install:
    """Replace the pipeline stages with fakes that record their keyword arguments."""

    def install(outputs: Mapping[str, object]) -> Calls:
        calls: Calls = {}

        def stage(name: str) -> Callable[..., object]:
            def record(_message: object, _info: object, **kwargs: object) -> object:
                calls[name] = kwargs
                return outputs[name]

            return record

        def async_stage(name: str) -> Callable[..., object]:
            async def record(
                _message: object, _info: object, **kwargs: object
            ) -> object:
                calls[name] = kwargs
                return outputs[name]

            return record

        monkeypatch.setattr(pipeline_module, "prepare_audio", async_stage("audio"))
        monkeypatch.setattr(pipeline_module, "prepare_media", async_stage("media"))
        monkeypatch.setattr(
            pipeline_module, "prepare_document", async_stage("document")
        )
        monkeypatch.setattr(pipeline_module, "build_user_content", stage("content"))
        monkeypatch.setattr(pipeline_module, "build_saved_user_text", stage("history"))
        return calls

    return install


@pytest.mark.asyncio
async def test_prepare_message_runs_the_stages_in_order(
    install_pipeline: Install,
) -> None:
    outputs = {
        "audio": "Распознано",
        "media": (["data:image/jpeg;base64,AA=="], [b"image-bytes"]),
        "document": ("Текст документа", "pdf"),
        "content": "Содержимое для LLM",
        "history": "Текст для истории",
    }
    calls = install_pipeline(outputs)

    await _prepare(_full_info("report.pdf"), make_settings(), MediaSlots())

    expected_order = ["audio", "media", "document", "content", "history"]
    assert list(calls) == expected_order, "the stages ran in a different order"


@pytest.mark.asyncio
async def test_prepare_message_returns_the_prepared_message(
    install_pipeline: Install,
) -> None:
    image_bytes = [b"\x89PNG-bytes"]
    user_content = "Содержимое для модели"
    saved_text = "Сохранённый текст"
    outputs = {
        "audio": "Голосовое сообщение",
        "media": (["data:image/png;base64,iVBO"], image_bytes),
        "document": ("Строки таблицы", "xlsx"),
        "content": user_content,
        "history": saved_text,
    }
    install_pipeline(outputs)

    result = await _prepare(_full_info("table.xlsx"), make_settings(), MediaSlots())

    expected = PreparedMessage(
        user_content=user_content,
        saved_user_text=saved_text,
        image_bytes=image_bytes,
    )
    assert result == expected, "the prepared message differs from the stage outputs"


@pytest.mark.asyncio
async def test_prepare_message_passes_downloader_and_settings_to_audio(
    install_pipeline: Install,
) -> None:
    app_settings = make_settings()
    outputs = {
        "audio": "Аудио",
        "media": (["data:image/gif;base64,R0lG"], [b"gif"]),
        "document": ("Абзац", "docx"),
        "content": "Контент",
        "history": "История",
    }
    calls = install_pipeline(outputs)

    await _prepare(_full_info("notes.docx"), app_settings, MediaSlots())

    expected = {"downloader": _download, "settings": app_settings}
    assert calls["audio"] == expected, "audio got other collaborators"


@pytest.mark.asyncio
async def test_prepare_message_passes_downloader_and_slots_to_media(
    install_pipeline: Install,
) -> None:
    media_slots = MediaSlots()
    outputs = {
        "audio": "Речь",
        "media": (["data:image/webp;base64,UklG"], [b"webp"]),
        "document": ("Раздел", "md"),
        "content": "Ввод",
        "history": "Запись",
    }
    calls = install_pipeline(outputs)

    await _prepare(_full_info("readme.md"), make_settings(), media_slots)

    expected = {"downloader": _download, "media_slots": media_slots}
    assert calls["media"] == expected, "media got other collaborators"


@pytest.mark.asyncio
async def test_prepare_message_passes_downloader_and_settings_to_document(
    install_pipeline: Install,
) -> None:
    app_settings = make_settings()
    outputs = {
        "audio": "Фраза",
        "media": (["data:image/jpeg;base64,/9j/"], [b"jpeg"]),
        "document": ("Глава первая", "epub"),
        "content": "Запрос",
        "history": "Журнал",
    }
    calls = install_pipeline(outputs)

    await _prepare(_full_info("book.epub"), app_settings, MediaSlots())

    expected = {"downloader": _download, "settings": app_settings}
    assert calls["document"] == expected, "document got other collaborators"


@pytest.mark.asyncio
async def test_prepare_message_passes_the_prepared_parts_to_user_content(
    install_pipeline: Install,
) -> None:
    transcript = "Распознано"
    image_urls = ["data:image/jpeg;base64,AA=="]
    document_text = "Текст документа"
    outputs = {
        "audio": transcript,
        "media": (image_urls, [b"image-bytes"]),
        "document": (document_text, "pdf"),
        "content": "Содержимое для LLM",
        "history": "Текст для истории",
    }
    calls = install_pipeline(outputs)

    await _prepare(_full_info("report.pdf"), make_settings(), MediaSlots())

    fields = ("transcribed_text", "image_urls", "document_text")
    passed = {field: calls["content"][field] for field in fields}
    expected = {
        "transcribed_text": transcript,
        "image_urls": image_urls,
        "document_text": document_text,
    }
    assert passed == expected, "user content got other prepared parts"


@pytest.mark.asyncio
async def test_prepare_message_keeps_document_format_out_of_user_content(
    install_pipeline: Install,
) -> None:
    outputs = {
        "audio": "Слова",
        "media": (["data:image/bmp;base64,Qk0="], [b"bmp"]),
        "document": ("Ячейки", "csv"),
        "content": "Текст запроса",
        "history": "Текст журнала",
    }
    calls = install_pipeline(outputs)

    await _prepare(_full_info("data.csv"), make_settings(), MediaSlots())

    format_field = "document_format"
    assert format_field not in calls["content"], "user content got the format"


@pytest.mark.asyncio
async def test_prepare_message_passes_document_format_to_saved_text(
    install_pipeline: Install,
) -> None:
    document_format = "odt"
    outputs = {
        "audio": "Диктовка",
        "media": (["data:image/tiff;base64,SUkq"], [b"tiff"]),
        "document": ("Документ", document_format),
        "content": "Ввод модели",
        "history": "Ввод истории",
    }
    calls = install_pipeline(outputs)

    await _prepare(_full_info("letter.odt"), make_settings(), MediaSlots())

    passed = calls["history"]["document_format"]
    assert passed == document_format, "the saved text got another document format"
