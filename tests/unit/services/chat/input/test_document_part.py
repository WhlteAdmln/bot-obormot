# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input document part."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from bot_obormot.errors import DocumentAPIError, DocumentTooLongError
from bot_obormot.services.chat.input import (
    MessageInfo,
)
from bot_obormot.services.chat.input import document_part as documents_module
from tests.support.message_input import make_message
from tests.support.settings import make_settings


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
            settings=make_settings(),
        )

    assert r"DOCUMENT: starting download: empty.pdf\nERROR forged entry" in caplog.text
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
            settings=make_settings(),
        )
