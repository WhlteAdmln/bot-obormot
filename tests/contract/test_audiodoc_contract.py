"""Compatibility checks against the shared audiodoc response examples."""

import json
from pathlib import Path

import aiohttp
import pytest

from bot.config import config
from bot.services.audio.client import transcribe_audio
from bot.services.documents.client import process_document
from bot.services.documents.response import validate_document_response

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "audiodoc_responses.json"
CONTRACT = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class FakeContent:
    def __init__(self, body: bytes):
        self.body = body

    async def iter_chunked(self, size):
        for offset in range(0, len(self.body), size):
            yield self.body[offset : offset + size]


class FakeResponse:
    status = 200
    content_length = None

    def __init__(self, payload):
        self.content = FakeContent(json.dumps(payload).encode("utf-8"))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_bot_transcription_client_accepts_shared_audiodoc_example(monkeypatch):
    payload = CONTRACT["transcribe"]
    assert set(payload) == {"text", "language", "duration"}
    assert isinstance(payload["text"], str)
    assert isinstance(payload["language"], str)
    assert isinstance(payload["duration"], (int, float))
    calls = {}

    class Session:
        def __init__(self, timeout, headers=None):
            calls["headers"] = headers

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, data):
            calls["url"] = url
            return FakeResponse(payload)

    monkeypatch.setattr(config, "WHISPER_API_URL", "http://audiodoc.test/transcribe")
    monkeypatch.setattr(config, "WHISPER_API_KEY", "whisper-test-key")
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    assert await transcribe_audio(b"audio", "voice.ogg") == payload["text"]
    assert calls["url"].endswith("/transcribe")
    assert calls["headers"] == {"Authorization": "Bearer whisper-test-key"}


@pytest.mark.asyncio
async def test_bot_document_client_accepts_shared_audiodoc_example(monkeypatch):
    payload = CONTRACT["process_document"]
    assert set(payload) == {"format", "text", "characters", "truncated"}
    assert validate_document_response(payload) is payload
    calls = {}

    class Session:
        def __init__(self, timeout, headers=None):
            calls["headers"] = headers

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def post(self, url, data):
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
