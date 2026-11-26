# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input document part."""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from bot_obormot.errors import DocumentAPIError, DocumentTooLongError
from bot_obormot.services.chat.input import document_part as documents_module
from tests.support.message_input import make_info, make_message
from tests.support.settings import make_settings


@pytest.mark.asyncio
async def test_prepare_document_downloads_the_document_file() -> None:
    file_id = "BQACAgIAAxkBAAIC-doc"
    requested: list[str] = []
    document = SimpleNamespace(file_id=file_id, file_name="blank.pdf")
    info = make_info(document=document, has_document=True)

    async def download(_message: object, actual_file_id: str) -> bytes:
        requested.append(actual_file_id)
        return b"%PDF-1.7 blank"

    async def process(_data: object, _filename: object) -> dict[str, object]:
        return {"text": "\t", "format": "pdf", "characters": 0}

    with pytest.raises(DocumentAPIError):
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
            settings=make_settings(),
        )
    assert requested == [file_id], "the document was not downloaded by its file id"


@pytest.mark.asyncio
async def test_prepare_document_passes_the_filename_to_the_processor() -> None:
    filename = "квартальный отчёт.docx"
    received: list[object] = []
    document = SimpleNamespace(file_id="doc-7781", file_name=filename)
    info = make_info(document=document, has_document=True)

    async def download(_message: object, _file_id: str) -> bytes:
        return b"PK\x03\x04docx"

    async def process(_data: object, actual_filename: object) -> dict[str, object]:
        received.append(actual_filename)
        return {"text": "", "format": "docx", "characters": 0}

    with pytest.raises(DocumentAPIError):
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
            settings=make_settings(),
        )
    assert received == [filename], "the processor got another filename"


@pytest.mark.asyncio
async def test_prepare_document_rejects_empty_extracted_text() -> None:
    expected_text = "Document contains no extractable text"
    document = SimpleNamespace(file_id="doc-id", file_name="empty.pdf")
    info = make_info(document=document, has_document=True)

    async def download(_message: object, _file_id: str) -> bytes:
        return b"document-bytes"

    async def process(_data: object, _filename: object) -> dict[str, object]:
        return {"text": "  ", "format": "pdf", "characters": 0}

    with pytest.raises(DocumentAPIError) as excinfo:
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
            settings=make_settings(),
        )
    assert expected_text in str(excinfo.value), "the empty text error is unclear"


@pytest.mark.asyncio
async def test_prepare_document_logs_an_escaped_filename(
    caplog: pytest.LogCaptureFixture,
) -> None:
    filename = "empty.pdf\nERROR forged entry"
    escaped_log_line = r"DOCUMENT: starting download: empty.pdf\nERROR forged entry"
    document = SimpleNamespace(file_id="doc-0042", file_name=filename)
    info = make_info(document=document, has_document=True)

    async def download(_message: object, _file_id: str) -> bytes:
        return b"scan"

    async def process(_data: object, _filename: object) -> dict[str, object]:
        return {"text": " \n ", "format": "pdf", "characters": 0}

    with (
        caplog.at_level(logging.INFO, logger=documents_module.logger.name),
        pytest.raises(DocumentAPIError),
    ):
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
            settings=make_settings(),
        )
    assert escaped_log_line in caplog.text, "the filename was not logged escaped"


@pytest.mark.asyncio
async def test_prepare_document_does_not_log_a_forged_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    filename = "notes.txt\nERROR forged entry"
    forged_line = "\nERROR forged entry"
    document = SimpleNamespace(file_id="doc-9", file_name=filename)
    info = make_info(document=document, has_document=True)

    async def download(_message: object, _file_id: str) -> bytes:
        return b"plain text"

    async def process(_data: object, _filename: object) -> dict[str, object]:
        return {"text": "   ", "format": "txt", "characters": 0}

    with (
        caplog.at_level(logging.INFO, logger=documents_module.logger.name),
        pytest.raises(DocumentAPIError),
    ):
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
            settings=make_settings(),
        )
    assert forged_line not in caplog.text, "a filename forged a new log line"


@pytest.mark.asyncio
async def test_prepare_document_rejects_truncated_extracted_text() -> None:
    document = SimpleNamespace(file_id="doc-id", file_name="large.pdf")
    info = make_info(document=document, has_document=True)

    async def download(_message: object, _file_id: object) -> bytes:
        return b"document-bytes"

    async def process(_data: object, _filename: object) -> dict[str, object]:
        return {
            "text": "Извлечённый фрагмент",
            "format": "pdf",
            "characters": 20,
            "truncated": True,
        }

    with pytest.raises(DocumentTooLongError) as excinfo:
        await documents_module.prepare_document(
            make_message(),
            info,
            downloader=download,
            document_processor=process,
            settings=make_settings(),
        )
    assert excinfo.type is DocumentTooLongError, "a truncated text was accepted"
