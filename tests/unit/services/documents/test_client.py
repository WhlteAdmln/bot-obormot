# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for documents client."""

import importlib
import logging
from typing import Self

import aiohttp
import pytest

from bot_obormot.errors import (
    DocumentAPIError,
    DocumentUnavailableError,
)
from bot_obormot.services.documents import process_document
from bot_obormot.services.documents.client import MAX_DOCUMENT_TEXT_LENGTH
from tests.support.audio_documents import FakeContent, json_body
from tests.support.settings import make_settings


@pytest.mark.asyncio
async def test_process_document_preserves_filename_sanitization_and_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Process document preserves filename sanitization and response."""
    calls = {}

    class Response:
        status = 200
        content_length = None

        def __init__(self) -> None:
            self.content = FakeContent(
                json_body(
                    {
                        "text": "Документ",
                        "format": "pdf",
                        "characters": 8,
                        "truncated": False,
                    }
                )
            )

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

    class Session:
        def __init__(self, timeout: object, headers: object | None = None) -> None:
            calls["timeout"] = timeout
            calls["headers"] = headers

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def post(self, url: str, data: object) -> Response:
            calls["url"] = url
            calls["data"] = data
            return Response()

    settings = make_settings(
        AUDIODOC_URL="http://documents.test",
        AUDIODOC_DOCUMENT_TIMEOUT=61,
        AUDIODOC_DOCUMENT_KEY="",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    with caplog.at_level(logging.INFO, logger="bot_obormot.services.documents.client"):
        result = await process_document(
            b"document-bytes",
            "../../report\nERROR forged.pdf",
            settings=settings,
        )

    assert result == {
        "text": "Документ",
        "format": "pdf",
        "characters": 8,
        "truncated": False,
    }
    assert r"filename=report\nERROR forged.pdf" in caplog.text
    assert "\nERROR forged.pdf" not in caplog.text
    assert calls["url"] == "http://documents.test/process-document"
    assert calls["timeout"].total == 61
    assert calls["headers"] == {}
    assert isinstance(calls["data"], aiohttp.FormData)
    multipart_filename = calls["data"]._fields[0][0]["filename"]
    assert multipart_filename == r"report\nERROR forged.pdf"
    assert "\r" not in multipart_filename
    assert "\n" not in multipart_filename

    form_fields = {field[0].get("name"): field[2] for field in calls["data"]._fields}
    assert form_fields["max_characters"] == str(MAX_DOCUMENT_TEXT_LENGTH)


@pytest.mark.asyncio
async def test_process_document_sends_bearer_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process document sends bearer api key."""
    calls = {}

    class Response:
        status = 200
        content_length = None
        content = FakeContent(
            json_body({"text": "Text", "format": "pdf", "characters": 4})
        )

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

    class Session:
        def __init__(self, timeout: object, headers: object | None = None) -> None:
            self.timeout = timeout
            calls["headers"] = headers

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def post(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    settings = make_settings(
        AUDIODOC_URL="http://documents.test",
        AUDIODOC_DOCUMENT_KEY="documents-secret",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    await process_document(b"document", "file.pdf", settings=settings)
    assert calls["headers"] == {"Authorization": "Bearer documents-secret"}


@pytest.mark.asyncio
async def test_process_document_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process document rejects oversized response."""
    documents_client = importlib.import_module("bot_obormot.services.documents.client")

    settings = make_settings(AUDIODOC_URL="http://documents.test")
    monkeypatch.setattr(documents_client, "MAX_SERVICE_RESPONSE_BYTES", 10)

    class Response:
        status = 200
        content_length = None
        content = FakeContent(
            json_body(
                {
                    "text": "document response is too long",
                    "format": "pdf",
                    "characters": 29,
                }
            )
        )

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

    class Session:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def post(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: Session())

    with pytest.raises(DocumentAPIError) as error:
        await process_document(b"document", "file.pdf", settings=settings)

    assert error.value.status == 502
    assert error.value.detail == "Document Engine response is too large"


@pytest.mark.asyncio
async def test_process_document_rejects_missing_url_and_preserves_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process document rejects missing url and preserves http status."""
    with pytest.raises(DocumentUnavailableError, match="not configured"):
        await process_document(
            b"data",
            "file.pdf",
            settings=make_settings(AUDIODOC_URL=""),
        )

    settings = make_settings(AUDIODOC_URL="http://documents.test")

    class Response:
        status = 415
        content_length = None

        def __init__(self) -> None:
            self.content = FakeContent(b"unsupported file type")

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

    class Session:
        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def post(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    monkeypatch.setattr(aiohttp, "ClientSession", lambda **_kwargs: Session())
    with pytest.raises(DocumentAPIError) as error:
        await process_document(b"data", "file.pdf", settings=settings)
    assert error.value.status == 415
    assert error.value.detail == "unsupported file type"


@pytest.mark.asyncio
async def test_process_document_maps_timeout_and_connection_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Process document maps timeout and connection errors."""
    settings = make_settings(AUDIODOC_URL="http://documents.test")

    def timeout_session(**_kwargs: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(aiohttp, "ClientSession", timeout_session)
    document_timeout_error = importlib.import_module(
        "bot_obormot.errors"
    ).DocumentTimeoutError

    with pytest.raises(document_timeout_error, match="timed out"):
        await process_document(b"data", "file.pdf", settings=settings)

    def failed_session(**_kwargs: object) -> None:
        msg = "connection refused"
        raise aiohttp.ClientConnectionError(msg)

    monkeypatch.setattr(aiohttp, "ClientSession", failed_session)
    with pytest.raises(DocumentUnavailableError, match="connection error"):
        await process_document(b"data", "file.pdf", settings=settings)
