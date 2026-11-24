# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for documents client."""

import logging
from collections.abc import Callable

import aiohttp
import pytest

from bot_obormot.errors import AppError
from bot_obormot.services import audiodoc_http
from bot_obormot.services.documents import process_document
from bot_obormot.services.documents.client import MAX_DOCUMENT_TEXT_LENGTH
from bot_obormot.settings import Settings
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


def _raising_session(error: BaseException) -> Callable[..., None]:
    def session(**_options: object) -> None:
        raise error

    return session


async def _failure(settings: Settings) -> tuple[str, str]:
    try:
        await process_document(b"%PDF-1.7", "scan.pdf", settings=settings)
    except AppError as error:
        return error.code, str(error)
    return "", ""


async def _sent_filename(monkeypatch: pytest.MonkeyPatch, filename: str) -> str | None:
    body = json_body({"text": "Текст", "format": "pdf", "characters": 5})
    session = _install(monkeypatch, FakeHTTPResponse(body=body))
    settings = make_settings(AUDIODOC_URL="http://documents.test")
    await process_document(b"%PDF", filename, settings=settings)
    sent, _value = form_fields(session.posts[0]["data"])["file"]
    return sent


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
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("/var/lib/bot/secrets.db", "secrets.db"),
        ("", "document"),
        ("q" * 300 + ".pdf", "q" * 255),
        ('a".pdf\r\nX-Injected: 1', 'a".pdf\\r\\nX-Injected: 1'),
    ],
    ids=["traversal", "absolute", "empty", "overlong", "header-injection"],
)
async def test_sends_a_bounded_single_line_basename(
    monkeypatch: pytest.MonkeyPatch, filename: str, expected: str
) -> None:
    sent = await _sent_filename(monkeypatch, filename)
    assert sent == expected, "the multipart filename must be a safe basename"


@pytest.mark.asyncio
async def test_rejects_a_missing_url() -> None:
    settings = make_settings(AUDIODOC_URL="")
    expected = ("document_unavailable", "AUDIODOC_URL is not configured")
    assert await _failure(settings) == expected, "a missing URL must be reported"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (415, b"unsupported file type", "HTTP 415: unsupported file type"),
        (500, b"E" * 1500, "HTTP 500: " + "E" * 1000),
        (500, b"E" * 3000, "HTTP 500: "),
        (
            200,
            b"<html>gateway</html>",
            "HTTP 502: Document Engine returned invalid JSON",
        ),
        (200, json_body([1, 2]), "HTTP 502: Invalid response from Document Engine"),
        (
            200,
            json_body({"text": None, "format": "pdf", "characters": 1}),
            "HTTP 502: Document Engine returned invalid text",
        ),
    ],
    ids=[
        "unsupported-type",
        "long-error-body",
        "error-body-over-limit",
        "not-json",
        "json-list",
        "null-text",
    ],
)
async def test_reports_a_bad_service_response(
    monkeypatch: pytest.MonkeyPatch, status: int, body: bytes, expected: str
) -> None:
    _install(monkeypatch, FakeHTTPResponse(status, body))
    settings = make_settings(AUDIODOC_URL="http://documents.test")
    failure = ("document_api_error", f"Document Engine {expected}")
    assert await _failure(settings) == failure, "the bad response is not reported"


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
    expected = (
        "document_api_error",
        "Document Engine HTTP 502: Document Engine response is too large",
    )
    assert await _failure(settings) == expected, "an oversized body must be refused"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), ("document_timeout", "Document processing timed out")),
        (
            aiohttp.ClientConnectionError("connection refused"),
            (
                "document_unavailable",
                "Document Engine connection error: connection refused",
            ),
        ),
    ],
    ids=["timeout", "connection-refused"],
)
async def test_maps_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    expected: tuple[str, str],
) -> None:
    monkeypatch.setattr(aiohttp, "ClientSession", _raising_session(error))
    settings = make_settings(AUDIODOC_URL="http://documents.test")
    assert await _failure(settings) == expected, "the transport failure is not mapped"
