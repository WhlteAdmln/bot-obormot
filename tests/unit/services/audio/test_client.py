# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for audio client."""

import logging

import aiohttp
import pytest

from bot_obormot.errors import (
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
)
from bot_obormot.services import audiodoc_http
from bot_obormot.services.audio import (
    transcribe_audio,
)
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
async def test_rejects_a_missing_audiodoc_url() -> None:
    settings = make_settings(AUDIODOC_URL="")
    with pytest.raises(AudiodocUnavailableError, match="not configured"):
        await transcribe_audio(b"audio", settings=settings)


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
    assert not leaked, "the log must not contain the text or the URL secret"


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
async def test_rejects_an_oversized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(audiodoc_http, "MAX_SERVICE_RESPONSE_BYTES", 10)
    _install(
        monkeypatch,
        FakeHTTPResponse(body=json_body({"text": "response is too long"})),
    )
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    with pytest.raises(AudiodocAPIError, match="response is too large"):
        await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_preserves_the_http_status_of_an_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, FakeHTTPResponse(503, b"backend unavailable"))
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    with pytest.raises(AudiodocAPIError, match="audiodoc HTTP 503"):
        await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_rejects_a_blank_transcription(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, FakeHTTPResponse(body=json_body({"text": "  "})))
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    with pytest.raises(AudiodocEmptyAudioError):
        await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_translates_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def timeout_session(**_kwargs: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(aiohttp, "ClientSession", timeout_session)
    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    with pytest.raises(AudiodocTimeoutError):
        await transcribe_audio(b"audio", settings=settings)
