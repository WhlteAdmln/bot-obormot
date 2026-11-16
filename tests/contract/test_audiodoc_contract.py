# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Compatibility checks against the shared audiodoc response examples."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Self

import aiohttp
import pytest
from jsonschema import Draft202012Validator

from bot.errors import AudiodocAPIError, DocumentAPIError
from bot.services.audio.client import transcribe_audio
from bot.services.documents.client import process_document
from bot.services.documents.response import validate_document_response
from bot.settings import Settings
from tests.support.fake_audiodoc import FakeAudiodoc, FakeResponseOptions
from tests.support.settings import make_settings

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "audiodoc_responses.json"
CONTRACT = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
OPENAPI_PATH = Path(__file__).parent / "audiodoc-openapi.json"
OPENAPI: dict[str, Any] = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
OPENAPI_VALIDATOR = Draft202012Validator(OPENAPI)


def _resolve_schema(schema: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if reference is None:
        return schema
    if not isinstance(reference, str) or not reference.startswith("#/"):
        msg = "Unsupported audiodoc schema reference"
        raise AssertionError(msg)

    resolved: Any = OPENAPI
    for part in reference[2:].split("/"):
        resolved = resolved[part.replace("~1", "/").replace("~0", "~")]
    if not isinstance(resolved, dict):
        msg = "Audiodoc schema reference does not resolve to an object"
        raise TypeError(msg)
    return resolved


def _operation(path: str) -> dict[str, Any]:
    return OPENAPI["paths"][path]["post"]


def _validate_response(path: str, status: int, payload: object) -> None:
    schema = _operation(path)["responses"][str(status)]["content"]["application/json"][
        "schema"
    ]
    OPENAPI_VALIDATOR.evolve(schema=schema).validate(payload)


def _real_client_settings(server: FakeAudiodoc) -> Settings:
    return make_settings(
        WHISPER_API_URL=f"{server.base_url}transcribe",
        WHISPER_API_KEY=server.whisper_api_key,
        DOCUMENT_API_URL=f"{server.base_url}process-document",
        DOCUMENT_API_KEY=server.document_api_key,
    )


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

    settings = make_settings(
        WHISPER_API_URL="http://audiodoc.test/transcribe",
        WHISPER_API_KEY="whisper-test-key",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    result = await transcribe_audio(b"audio", "voice.ogg", settings=settings)
    assert result == payload["text"]
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

    settings = make_settings(
        DOCUMENT_API_URL="http://audiodoc.test/process-document",
        DOCUMENT_API_KEY="document-test-key",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", Session)

    result = await process_document(
        b"Example document text.",
        "note.txt",
        settings=settings,
    )
    assert result == payload
    assert calls["url"].endswith("/process-document")
    assert calls["headers"] == {"Authorization": "Bearer document-test-key"}
    fields = {field[0].get("name"): field[2] for field in calls["data"]._fields}
    assert fields["max_characters"] == "11264"


def test_shared_audiodoc_response_examples_match_openapi() -> None:
    """Validate the shared successful response examples against OpenAPI."""
    _validate_response("/transcribe", 200, CONTRACT["transcribe"])
    _validate_response("/process-document", 200, CONTRACT["process_document"])


@pytest.mark.asyncio
async def test_real_bot_requests_match_audiodoc_openapi() -> None:
    """Validate real client requests and response parsing over local HTTP."""
    async with FakeAudiodoc() as server:
        settings = _real_client_settings(server)

        assert (
            await transcribe_audio(b"audio", "voice.ogg", settings=settings)
            == CONTRACT["transcribe"]["text"]
        )
        assert (
            await process_document(b"document", "note.txt", settings=settings)
            == CONTRACT["process_document"]
        )

        expected = (
            ("/transcribe", server.whisper_api_key),
            ("/process-document", server.document_api_key),
        )
        assert len(server.requests) == len(expected)
        for request, (path, api_key) in zip(server.requests, expected, strict=True):
            operation = _operation(path)
            assert request.method == "POST"
            assert request.path == path
            assert request.content_type == "multipart/form-data"

            authorization = [
                parameter
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "header"
                and parameter["name"].lower() == "authorization"
            ]
            assert len(authorization) == 1
            assert request.authorization == f"Bearer {api_key}"
            OPENAPI_VALIDATOR.evolve(schema=authorization[0]["schema"]).validate(
                request.authorization
            )

            request_schema = operation["requestBody"]["content"]["multipart/form-data"][
                "schema"
            ]
            resolved_request_schema = _resolve_schema(request_schema)
            properties = set(resolved_request_schema["properties"])
            request_fields = set(request.fields)
            assert request_fields <= properties
            assert set(resolved_request_schema.get("required", [])) <= request_fields

            payload: dict[str, object] = dict(request.fields)
            if "max_characters" in payload:
                payload["max_characters"] = int(payload["max_characters"])
            OPENAPI_VALIDATOR.evolve(schema=request_schema).validate(payload)


@pytest.mark.parametrize(
    ("path", "status"),
    [
        (path, int(status))
        for path, operations in OPENAPI["paths"].items()
        for status in operations.get("post", {}).get("responses", {})
        if int(status) >= 400
    ],
)
@pytest.mark.asyncio
async def test_bot_handles_every_documented_audiodoc_error_status(
    path: str,
    status: int,
) -> None:
    """Parse every documented error response through the real HTTP clients."""
    endpoint = "transcribe" if path == "/transcribe" else "process-document"
    async with FakeAudiodoc() as server:
        settings = _real_client_settings(server)
        server.set_behavior(endpoint, FakeResponseOptions(status=status))

        if endpoint == "transcribe":
            with pytest.raises(AudiodocAPIError, match=f"Whisper HTTP {status}"):
                await transcribe_audio(b"audio", "voice.ogg", settings=settings)
        else:
            with pytest.raises(DocumentAPIError) as error:
                await process_document(b"document", "note.txt", settings=settings)
            assert error.value.status == status

        response_endpoint, response_status, payload = server.responses[-1]
        assert response_endpoint == endpoint
        assert response_status == status
        _validate_response(path, status, payload)
