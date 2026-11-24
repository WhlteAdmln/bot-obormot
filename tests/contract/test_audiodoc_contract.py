# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Compatibility checks against the shared audiodoc response examples."""

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from jsonschema import Draft202012Validator

from bot_obormot.errors import AudiodocAPIError, DocumentAPIError
from bot_obormot.services.audio.client import transcribe_audio
from bot_obormot.services.documents.client import process_document
from bot_obormot.services.documents.response import validate_document_response
from bot_obormot.settings import Settings
from tests.support.audio_documents import (
    FakeHTTPResponse,
    FakeHTTPSession,
    form_fields,
    json_body,
)
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
        AUDIODOC_URL=server.base_url.rstrip("/"),
        AUDIODOC_AUDIO_KEY=server.whisper_api_key,
        AUDIODOC_DOCUMENT_KEY=server.document_api_key,
    )


@pytest.mark.asyncio
async def test_bot_transcription_client_accepts_shared_audiodoc_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = CONTRACT["transcribe"]
    assert set(payload) == {"text", "language", "duration"}
    assert isinstance(payload["text"], str)
    assert isinstance(payload["language"], str)
    assert isinstance(payload["duration"], (int, float))
    session = FakeHTTPSession(FakeHTTPResponse(body=json_body(payload)))

    settings = make_settings(
        AUDIODOC_URL="http://audiodoc.test",
        AUDIODOC_AUDIO_KEY="whisper-test-key",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", session)

    result = await transcribe_audio(b"audio", "voice.ogg", settings=settings)
    assert result == payload["text"]
    assert session.posts[0]["url"].endswith("/transcribe")
    assert session.options["headers"] == {"Authorization": "Bearer whisper-test-key"}


@pytest.mark.asyncio
async def test_bot_document_client_accepts_shared_audiodoc_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = CONTRACT["process_document"]
    assert set(payload) == {"format", "text", "characters", "truncated"}
    assert validate_document_response(payload) is payload
    session = FakeHTTPSession(FakeHTTPResponse(body=json_body(payload)))

    settings = make_settings(
        AUDIODOC_URL="http://audiodoc.test",
        AUDIODOC_DOCUMENT_KEY="document-test-key",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", session)

    result = await process_document(
        b"Example document text.",
        "note.txt",
        settings=settings,
    )
    assert result == payload
    assert session.posts[0]["url"].endswith("/process-document")
    assert session.options["headers"] == {"Authorization": "Bearer document-test-key"}
    fields = form_fields(session.posts[0]["data"])
    expected_max_characters = "11264"
    assert fields["max_characters"][1] == expected_max_characters


def test_shared_audiodoc_response_examples_match_openapi() -> None:
    _validate_response("/transcribe", 200, CONTRACT["transcribe"])
    _validate_response("/process-document", 200, CONTRACT["process_document"])


def _check_request(request: object, path: str, api_key: str) -> None:
    operation = _operation(path)
    expected_method = "POST"
    assert request.method == expected_method
    assert request.path == path
    expected_content_type = "multipart/form-data"
    assert request.content_type == expected_content_type

    expected_in = "header"
    expected_lower = "authorization"
    authorization = [
        parameter
        for parameter in operation.get("parameters", [])
        if parameter["in"] == expected_in
        and parameter["name"].lower() == expected_lower
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
    limit_field = "max_characters"
    if limit_field in payload:
        payload["max_characters"] = int(payload["max_characters"])
    OPENAPI_VALIDATOR.evolve(schema=request_schema).validate(payload)


@pytest.mark.asyncio
async def test_real_bot_requests_match_audiodoc_openapi() -> None:
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
            _check_request(request, path, api_key)


@pytest.mark.parametrize(
    ("path", "status"),
    [
        (path, int(status))
        for path, operations in OPENAPI["paths"].items()
        for status in operations.get("post", {}).get("responses", {})
        if int(status) >= HTTPStatus.BAD_REQUEST
    ],
)
@pytest.mark.asyncio
async def test_bot_handles_every_documented_audiodoc_error_status(
    path: str,
    status: int,
) -> None:
    expected_path = "/transcribe"
    endpoint = "transcribe" if path == expected_path else "process-document"
    async with FakeAudiodoc() as server:
        settings = _real_client_settings(server)
        server.set_behavior(endpoint, FakeResponseOptions(status=status))

        expected_endpoint = "transcribe"
        if endpoint == expected_endpoint:
            with pytest.raises(AudiodocAPIError, match=f"audiodoc HTTP {status}"):
                await transcribe_audio(b"audio", "voice.ogg", settings=settings)
        else:
            with pytest.raises(DocumentAPIError) as error:
                await process_document(b"document", "note.txt", settings=settings)
            assert error.value.status == status

        response_endpoint, response_status, payload = server.responses[-1]
        assert response_endpoint == endpoint
        assert response_status == status
        _validate_response(path, status, payload)
