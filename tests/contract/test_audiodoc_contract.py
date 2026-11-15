# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Compatibility checks against the shared audiodoc response examples."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Self

import aiohttp
import pytest

from bot.config import config
from bot.services.audio.client import transcribe_audio
from bot.services.documents.client import process_document
from bot.services.documents.response import validate_document_response

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "audiodoc_responses.json"
CONTRACT = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class FakeContent:
    """Fake content."""

    def __init__(self, body: bytes) -> None:
        """Initializes the test double."""
        self.body = body

    async def iter_chunked(self, size: object) -> AsyncIterator[bytes]:
        """Iter chunked."""
        for offset in range(0, len(self.body), size):
            yield self.body[offset : offset + size]


class FakeResponse:
    """Fake response."""

    status = 200
    content_length = None

    def __init__(self, payload: object) -> None:
        """Initializes the test double."""
        self.content = FakeContent(json.dumps(payload).encode("utf-8"))

    async def __aenter__(self) -> Self:
        """Enters the async context."""
        return self

    async def __aexit__(self, *_args: object) -> bool:
        """Leaves the async context."""
        return False


@pytest.mark.asyncio
async def test_bot_transcription_client_accepts_shared_audiodoc_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot transcription client accepts shared audiodoc example."""
    payload = CONTRACT["transcribe"]
    assert set(payload) == {"text", "language", "duration"}
    assert isinstance(payload["text"], str)
    assert isinstance(payload["language"], str)
    assert isinstance(payload["duration"], (int, float))
    calls = {}

    class Session:
        def __init__(self, timeout: object, headers: object | None = None) -> None:
            self.timeout = timeout
            calls["headers"] = headers

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def post(self, url: str, data: object) -> FakeResponse:
            self.posted_data = data
            calls["url"] = url
            return FakeResponse(payload)

    monkeypatch.setattr(config, "WHISPER_API_URL", "http://audiodoc.test/transcribe")
    monkeypatch.setattr(config, "WHISPER_API_KEY", "whisper-test-key")
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    assert await transcribe_audio(b"audio", "voice.ogg") == payload["text"]
    assert calls["url"].endswith("/transcribe")
    assert calls["headers"] == {"Authorization": "Bearer whisper-test-key"}


@pytest.mark.asyncio
async def test_bot_document_client_accepts_shared_audiodoc_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bot document client accepts shared audiodoc example."""
    payload = CONTRACT["process_document"]
    assert set(payload) == {"format", "text", "characters", "truncated"}
    assert validate_document_response(payload) is payload
    calls = {}

    class Session:
        def __init__(self, timeout: object, headers: object | None = None) -> None:
            self.timeout = timeout
            calls["headers"] = headers

        async def __aenter__(self) -> Self:
            return self

        async def __aexit__(self, *_args: object) -> bool:
            return False

        def post(self, url: str, data: object) -> FakeResponse:
            calls["url"] = url
            calls["data"] = data
            return FakeResponse(payload)

    monkeypatch.setattr(
        config, "DOCUMENT_API_URL", "http://audiodoc.test/process-document"
    )
    monkeypatch.setattr(config, "DOCUMENT_API_KEY", "document-test-key")
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    result = await process_document(b"Example document text.", "note.txt")
    assert result == payload
    assert calls["url"].endswith("/process-document")
    assert calls["headers"] == {"Authorization": "Bearer document-test-key"}
    fields = {field[0].get("name"): field[2] for field in calls["data"]._fields}
    assert fields["max_characters"] == "11264"
