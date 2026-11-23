# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for audio client."""

import importlib
import logging
from typing import Self

import aiohttp
import pytest

from bot_obormot.errors import (
    AudiodocAPIError,
    AudiodocEmptyAudioError,
    AudiodocTimeoutError,
    AudiodocUnavailableError,
)
from bot_obormot.services.audio import (
    transcribe_audio,
)
from tests.support.audio_documents import FakeContent, json_body
from tests.support.settings import make_settings


@pytest.mark.asyncio
async def test_transcribe_audio_rejects_missing_whisper_url() -> None:
    """Transcribe audio rejects missing audiodoc url."""
    settings = make_settings(AUDIODOC_URL="")
    with pytest.raises(AudiodocUnavailableError, match="not configured"):
        await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_transcribe_audio_posts_multipart_and_strips_result(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Transcribe audio posts multipart and strips result."""
    calls = {}

    class Response:
        status = 200
        content_length = None

        def __init__(self) -> None:
            self.content = FakeContent(json_body({"text": "  распознанный текст  "}))

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
            calls.update(url=url, data=data)
            return Response()

    settings = make_settings(
        AUDIODOC_URL="http://whisper.test?token=private",
        AUDIODOC_AUDIO_TIMEOUT=37,
        AUDIODOC_AUDIO_KEY="",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    with caplog.at_level(logging.INFO, logger="bot_obormot.services.audio.client"):
        result = await transcribe_audio(
            b"audio-bytes",
            "voice\nERROR forged.ogg",
            settings=settings,
        )

    assert result == "распознанный текст"
    assert calls["url"] == "http://whisper.test/transcribe?token=private"
    assert "распознанный текст" not in caplog.text
    assert "token=private" not in caplog.text
    assert r"filename=voice\nERROR forged.ogg" in caplog.text
    assert "\nERROR forged.ogg" not in caplog.text
    assert caplog.text.count("audiodoc transcription received: 18 chars") == 1
    assert calls["timeout"].total == 37
    assert calls["headers"] == {}
    assert isinstance(calls["data"], aiohttp.FormData)
    multipart_filename = calls["data"]._fields[0][0]["filename"]
    assert multipart_filename == r"voice\nERROR forged.ogg"
    assert "\r" not in multipart_filename
    assert "\n" not in multipart_filename


@pytest.mark.asyncio
async def test_transcribe_audio_sends_bearer_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transcribe audio sends bearer api key."""
    calls = {}

    class Response:
        status = 200
        content_length = None
        content = FakeContent(json_body({"text": "recognized"}))

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
        AUDIODOC_URL="http://whisper.test",
        AUDIODOC_AUDIO_KEY="whisper-secret",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    assert await transcribe_audio(b"audio", settings=settings) == "recognized"
    assert calls["headers"] == {"Authorization": "Bearer whisper-secret"}


@pytest.mark.asyncio
async def test_transcribe_audio_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transcribe audio rejects oversized response."""
    audio_client = importlib.import_module("bot_obormot.services.audio.client")

    settings = make_settings(AUDIODOC_URL="http://whisper.test")
    monkeypatch.setattr(audio_client, "MAX_SERVICE_RESPONSE_BYTES", 10)

    class Response:
        status = 200
        content_length = None
        content = FakeContent(json_body({"text": "response is too long"}))

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

    with pytest.raises(AudiodocAPIError, match="response is too large"):
        await transcribe_audio(b"audio", settings=settings)


@pytest.mark.asyncio
async def test_transcribe_audio_preserves_api_empty_and_timeout_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Transcribe audio preserves api empty and timeout errors."""
    settings = make_settings(AUDIODOC_URL="http://whisper.test")

    class Response:
        content_length = None

        def __init__(self, status: int = 200, body: bytes = b'{"text": ""}') -> None:
            self.status = status
            self.content = FakeContent(body)

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

    class Session:
        def __init__(self, response: object) -> None:
            self.response = response

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def post(self, *_args: object, **_kwargs: object) -> object:
            return self.response

    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda **_kwargs: Session(Response(503, b"backend unavailable")),
    )
    with pytest.raises(AudiodocAPIError, match="audiodoc HTTP 503"):
        await transcribe_audio(b"audio", settings=settings)

    monkeypatch.setattr(
        aiohttp,
        "ClientSession",
        lambda **_kwargs: Session(Response(body=json_body({"text": "  "}))),
    )
    with pytest.raises(AudiodocEmptyAudioError):
        await transcribe_audio(b"audio", settings=settings)

    def timeout_session(**_kwargs: object) -> None:
        raise TimeoutError

    monkeypatch.setattr(aiohttp, "ClientSession", timeout_session)
    with pytest.raises(AudiodocTimeoutError):
        await transcribe_audio(b"audio", settings=settings)
