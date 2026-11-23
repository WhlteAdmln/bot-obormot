# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for documents client."""

import logging

import aiohttp
import pytest

from bot_obormot.errors import (
    DocumentAPIError,
    DocumentTimeoutError,
    DocumentUnavailableError,
)
from bot_obormot.services import audiodoc_http
from bot_obormot.services.documents import process_document
from bot_obormot.services.documents.client import MAX_DOCUMENT_TEXT_LENGTH
from tests.support.audio_documents import (
    FakeHTTPResponse,
    FakeHTTPSession,
    form_fields,
    json_body,
)
from tests.support.settings import make_settings


def _install(
    monkeypatch: pytest.MonkeyPatch,
    response: FakeHTTPResponse,
) -> FakeHTTPSession:
    session = FakeHTTPSession(response)
    monkeypatch.setattr(aiohttp, "ClientSession", session)
    return session


def _document_payload() -> dict[str, object]:
    return {"text": "Документ", "format": "pdf", "characters": 8, "truncated": False}


async def _process_forged_name(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> tuple[dict[str, object], FakeHTTPSession]:
    session = _install(
        monkeypatch, FakeHTTPResponse(body=json_body(_document_payload()))
    )
    settings = make_settings(
        AUDIODOC_URL="http://documents.test",
        AUDIODOC_DOCUMENT_TIMEOUT=61,
        AUDIODOC_DOCUMENT_KEY="",
    )
    logger = "bot_obormot.services.documents.client"
    with caplog.at_level(logging.INFO, logger=logger):
        result = await process_document(
            b"document-bytes",
            "../../report\nERROR forged.pdf",
            settings=settings,
        )
    return result, session


@pytest.mark.asyncio
async def test_returns_the_parsed_response(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result, _session = await _process_forged_name(monkeypatch, caplog)
    assert result == _document_payload(), "the response must be returned unchanged"


@pytest.mark.asyncio
async def test_logs_the_filename_with_escaped_line_breaks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _process_forged_name(monkeypatch, caplog)
    expected = r"filename=report\nERROR forged.pdf"
    assert expected in caplog.text, "the log must contain the escaped filename"


@pytest.mark.asyncio
async def test_does_not_log_a_raw_line_break_from_the_filename(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _process_forged_name(monkeypatch, caplog)
    forged = "\nERROR forged.pdf"
    assert forged not in caplog.text, "a filename must not forge a log line"


@pytest.mark.asyncio
async def test_posts_to_the_process_document_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _process_forged_name(monkeypatch, caplog)
    expected = "http://documents.test/process-document"
    assert session.posts[0]["url"] == expected, "the endpoint URL is wrong"


@pytest.mark.asyncio
async def test_uses_the_configured_document_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _process_forged_name(monkeypatch, caplog)
    expected = aiohttp.ClientTimeout(total=61)
    assert session.options["timeout"] == expected, "the timeout is wrong"


@pytest.mark.asyncio
async def test_sends_no_authorization_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _process_forged_name(monkeypatch, caplog)
    assert session.options["headers"] == {}, "no header is expected without a key"


@pytest.mark.asyncio
async def test_sends_a_basename_without_line_breaks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _process_forged_name(monkeypatch, caplog)
    filename, _value = form_fields(session.posts[0]["data"])["file"]
    expected = r"report\nERROR forged.pdf"
    assert filename == expected, "the multipart filename must be sanitized"


@pytest.mark.asyncio
async def test_sends_the_text_length_limit(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _process_forged_name(monkeypatch, caplog)
    _filename, value = form_fields(session.posts[0]["data"])["max_characters"]
    expected = str(MAX_DOCUMENT_TEXT_LENGTH)
    assert value == expected, "the text limit must be sent"


@pytest.mark.asyncio
async def test_sends_the_bearer_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "documents-secret-Ж"
    body = json_body({"text": "Text", "format": "pdf", "characters": 4})
    session = _install(monkeypatch, FakeHTTPResponse(body=body))
    settings = make_settings(
        AUDIODOC_URL="http://documents.test",
        AUDIODOC_DOCUMENT_KEY=key,
    )
    await process_document(b"document", "file.pdf", settings=settings)
    expected = {"Authorization": f"Bearer {key}"}
    assert session.options["headers"] == expected, "the bearer key is missing"


@pytest.mark.asyncio
async def test_rejects_an_oversized_response_as_bad_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(audiodoc_http, "MAX_SERVICE_RESPONSE_BYTES", 10)
    body = json_body(
        {"text": "document response is too long", "format": "pdf", "characters": 29}
    )
    _install(monkeypatch, FakeHTTPResponse(body=body))
    settings = make_settings(AUDIODOC_URL="http://documents.test")
    with pytest.raises(DocumentAPIError) as error:
        await process_document(b"document", "file.pdf", settings=settings)
    expected = (502, "Document Engine response is too large")
    actual = (error.value.status, error.value.detail)
    assert actual == expected, "an oversized response must be a bad gateway"


@pytest.mark.asyncio
async def test_rejects_a_missing_url() -> None:
    settings = make_settings(AUDIODOC_URL="")
    with pytest.raises(DocumentUnavailableError, match="not configured"):
        await process_document(b"data", "file.pdf", settings=settings)


@pytest.mark.asyncio
async def test_preserves_the_http_status_of_an_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = 415
    _install(monkeypatch, FakeHTTPResponse(status, b"unsupported file type"))
    settings = make_settings(AUDIODOC_URL="http://documents.test")
    with pytest.raises(DocumentAPIError) as error:
        await process_document(b"data", "file.pdf", settings=settings)
    assert error.value.status == status, "the HTTP status must be preserved"


@pytest.mark.asyncio
async def test_maps_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout_session(**_kwargs: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(aiohttp, "ClientSession", timeout_session)
    settings = make_settings(AUDIODOC_URL="http://documents.test")
    with pytest.raises(DocumentTimeoutError, match="timed out"):
        await process_document(b"data", "file.pdf", settings=settings)


@pytest.mark.asyncio
async def test_maps_a_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed_session(**_kwargs: object) -> None:
        msg = "connection refused"
        raise aiohttp.ClientConnectionError(msg)

    monkeypatch.setattr(aiohttp, "ClientSession", failed_session)
    settings = make_settings(AUDIODOC_URL="http://documents.test")
    with pytest.raises(DocumentUnavailableError, match="connection error"):
        await process_document(b"data", "file.pdf", settings=settings)
