# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for audio client."""

import logging
from collections.abc import Callable

import aiohttp
import pytest

from bot_obormot.errors import AppError
from bot_obormot.services import audiodoc_http
from bot_obormot.services.audio import (
    transcribe_audio,
)
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


def _raising_session(error: BaseException) -> Callable[..., None]:
    def session(**_options: object) -> None:
        raise error

    return session


async def _failure(settings: Settings) -> tuple[str, str]:
    try:
        await transcribe_audio(b"\x00\x01ogg-frames", "voice.ogg", settings=settings)
    except AppError as error:
        return error.code, str(error)
    return "", ""


async def _sent_filename(monkeypatch: pytest.MonkeyPatch, filename: str) -> str | None:
    session = _install(monkeypatch, FakeHTTPResponse(body=json_body({"text": "ок"})))
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    await transcribe_audio(b"opus", filename, settings=settings)
    sent, _value = form_fields(session.posts[0]["data"])["file"]
    return sent


async def _transcribe_forged_name(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> tuple[str, FakeHTTPSession]:
    session = _install(
        monkeypatch,
        FakeHTTPResponse(body=json_body({"text": "  распознанный текст  "})),
    )
    settings = make_settings(
        AUDIODOC_URL="http://whisper.test?token=private",
        AUDIODOC_AUDIO_TIMEOUT=37,
        AUDIODOC_AUDIO_KEY="",
    )
    with caplog.at_level(logging.INFO, logger="bot_obormot.services.audio.client"):
        result = await transcribe_audio(
            b"audio-bytes", "voice\nERROR forged.ogg", settings=settings
        )
    return result, session


@pytest.mark.asyncio
async def test_returns_the_stripped_transcription(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    result, _session = await _transcribe_forged_name(monkeypatch, caplog)
    expected = "распознанный текст"
    assert result == expected, "the transcription must be stripped"


@pytest.mark.asyncio
async def test_posts_to_the_transcribe_endpoint_keeping_the_query(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _transcribe_forged_name(monkeypatch, caplog)
    expected = "http://whisper.test/transcribe?token=private"
    assert session.posts[0]["url"] == expected, "the endpoint URL is wrong"


@pytest.mark.asyncio
async def test_does_not_log_the_transcription_or_the_url_secret(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _transcribe_forged_name(monkeypatch, caplog)
    secrets = ("распознанный текст", "token=private")
    leaked = [secret for secret in secrets if secret in caplog.text]
    expected_empty = []
    assert leaked == expected_empty, (
        "the log must not contain the text or the URL secret"
    )


@pytest.mark.asyncio
async def test_logs_the_filename_with_escaped_line_breaks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _transcribe_forged_name(monkeypatch, caplog)
    expected = r"filename=voice\nERROR forged.ogg"
    assert expected in caplog.text, "the log must contain the escaped filename"


@pytest.mark.asyncio
async def test_does_not_log_a_raw_line_break_from_the_filename(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _transcribe_forged_name(monkeypatch, caplog)
    forged = "\nERROR forged.ogg"
    assert forged not in caplog.text, "a filename must not forge a log line"


@pytest.mark.asyncio
async def test_logs_the_received_length_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await _transcribe_forged_name(monkeypatch, caplog)
    line = "audiodoc transcription received: 18 chars"
    assert caplog.text.count(line) == 1, "the received length must be logged once"


@pytest.mark.asyncio
async def test_uses_the_configured_audio_timeout(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _transcribe_forged_name(monkeypatch, caplog)
    expected = aiohttp.ClientTimeout(total=37)
    assert session.options["timeout"] == expected, "the timeout is wrong"


@pytest.mark.asyncio
async def test_sends_no_authorization_without_a_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _transcribe_forged_name(monkeypatch, caplog)
    assert session.options["headers"] == {}, "no header is expected without a key"


@pytest.mark.asyncio
async def test_sends_a_multipart_filename_without_line_breaks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _result, session = await _transcribe_forged_name(monkeypatch, caplog)
    filename, _value = form_fields(session.posts[0]["data"])["file"]
    expected = r"voice\nERROR forged.ogg"
    assert filename == expected, "the multipart filename must be escaped"


@pytest.mark.asyncio
async def test_sends_the_bearer_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    key = "whisper-secret-Ω"
    session = _install(
        monkeypatch,
        FakeHTTPResponse(body=json_body({"text": "recognized"})),
    )
    settings = make_settings(AUDIODOC_URL="http://whisper.test", AUDIODOC_AUDIO_KEY=key)
    await transcribe_audio(b"audio", settings=settings)
    expected = {"Authorization": f"Bearer {key}"}
    assert session.options["headers"] == expected, "the bearer key is missing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("", "audio.ogg"),
        ("n" * 400 + ".ogg", "n" * 255),
        ('voice".ogg\r\nX-Injected: 1', 'voice".ogg\\r\\nX-Injected: 1'),
    ],
    ids=["empty", "overlong", "header-injection"],
)
async def test_sends_a_bounded_single_line_filename(
    monkeypatch: pytest.MonkeyPatch, filename: str, expected: str
) -> None:
    sent = await _sent_filename(monkeypatch, filename)
    assert sent == expected, "the multipart filename must be safe"


@pytest.mark.asyncio
async def test_rejects_a_missing_audiodoc_url() -> None:
    settings = make_settings(AUDIODOC_URL="")
    expected = ("audiodoc_unavailable", "AUDIODOC_URL is not configured")
    assert await _failure(settings) == expected, "a missing URL must be reported"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (
            503,
            b"backend unavailable",
            ("audiodoc_api_error", "audiodoc HTTP 503: backend unavailable"),
        ),
        (
            401,
            b"\xff\xfe",
            ("audiodoc_api_error", "audiodoc HTTP 401: \ufffd\ufffd"),
        ),
        (
            500,
            b"E" * 1500,
            ("audiodoc_api_error", "audiodoc HTTP 500: " + "E" * 1000 + " [truncated]"),
        ),
        (
            500,
            b"E" * 3000,
            ("audiodoc_api_error", "audiodoc HTTP 500: " + "E" * 1000 + " [truncated]"),
        ),
        (
            200,
            b"<html>gateway</html>",
            ("audiodoc_api_error", "audiodoc returned invalid JSON"),
        ),
        (
            200,
            json_body(["text"]),
            ("audiodoc_api_error", "audiodoc returned an unexpected response"),
        ),
        (
            200,
            json_body({"text": " \n\t "}),
            ("audiodoc_empty_audio", "No speech detected in audio"),
        ),
        (200, json_body({}), ("audiodoc_empty_audio", "No speech detected in audio")),
    ],
    ids=[
        "server-error",
        "undecodable-error-body",
        "long-error-body",
        "error-body-over-limit",
        "not-json",
        "json-list",
        "blank-text",
        "no-text",
    ],
)
async def test_reports_a_bad_service_response(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    body: bytes,
    expected: tuple[str, str],
) -> None:
    _install(monkeypatch, FakeHTTPResponse(status, body))
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    assert await _failure(settings) == expected, "the bad response is not reported"


@pytest.mark.asyncio
async def test_rejects_an_oversized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audiodoc_http, "MAX_SERVICE_RESPONSE_BYTES", 10)
    _install(
        monkeypatch,
        FakeHTTPResponse(body=json_body({"text": "response is too long"})),
    )
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    expected = ("audiodoc_api_error", "audiodoc response is too large")
    assert await _failure(settings) == expected, "an oversized body must be refused"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), ("audiodoc_timeout", "audiodoc request timed out")),
        (
            aiohttp.ClientConnectionError("connection refused"),
            ("audiodoc_unavailable", "audiodoc connection error: connection refused"),
        ),
    ],
    ids=["timeout", "connection-refused"],
)
async def test_translates_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
    expected: tuple[str, str],
) -> None:
    monkeypatch.setattr(aiohttp, "ClientSession", _raising_session(error))
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    assert await _failure(settings) == expected, "the transport failure is not mapped"
