# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Compatibility checks against the shared audiodoc response examples."""

import json
from http import HTTPStatus
from pathlib import Path
from typing import Any, cast

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
from tests.support.fake_audiodoc import (
    Endpoint,
    FakeAudiodoc,
    FakeRequest,
    FakeResponseOptions,
)
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
    operation: dict[str, Any] = OPENAPI["paths"][path]["post"]
    return operation


def _schema_errors(schema: dict[str, Any], instance: object) -> list[str]:
    validator = OPENAPI_VALIDATOR.evolve(schema=schema)
    return [error.message for error in validator.iter_errors(instance)]


def _response_errors(path: str, status: int, payload: object) -> list[str]:
    schema = _operation(path)["responses"][str(status)]["content"]["application/json"][
        "schema"
    ]
    return _schema_errors(schema, payload)


def _real_client_settings(server: FakeAudiodoc) -> Settings:
    return make_settings(
        AUDIODOC_URL=server.base_url.rstrip("/"),
        AUDIODOC_AUDIO_KEY=server.whisper_api_key,
        AUDIODOC_DOCUMENT_KEY=server.document_api_key,
    )


async def _transcribe_with_fake_session(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, FakeHTTPSession]:
    payload = CONTRACT["transcribe"]
    session = FakeHTTPSession(FakeHTTPResponse(body=json_body(payload)))
    settings = make_settings(
        AUDIODOC_URL="http://audiodoc.test",
        AUDIODOC_AUDIO_KEY="whisper-test-key",
    )
    monkeypatch.setattr(aiohttp, "ClientSession", session)
    result = await transcribe_audio(b"audio", "voice.ogg", settings=settings)
    return result, session


async def _process_with_fake_session(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[object, FakeHTTPSession]:
    payload = CONTRACT["process_document"]
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
    return result, session


def test_shared_transcription_example_has_the_documented_fields() -> None:
    expected_fields = {"text", "language", "duration"}
    payload = CONTRACT["transcribe"]
    assert set(payload) == expected_fields, "the transcription example fields differ"


@pytest.mark.parametrize(
    ("field", "expected_types"),
    [("text", (str,)), ("language", (str,)), ("duration", (int, float))],
)
def test_shared_transcription_example_fields_have_the_documented_types(
    field: str,
    expected_types: tuple[type, ...],
) -> None:
    value = CONTRACT["transcribe"][field]
    assert isinstance(value, expected_types), f"{field} has the wrong type"


@pytest.mark.asyncio
async def test_bot_transcription_client_accepts_shared_audiodoc_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_text = CONTRACT["transcribe"]["text"]
    result, _session = await _transcribe_with_fake_session(monkeypatch)
    assert result == expected_text, "the transcription text differs"


@pytest.mark.asyncio
async def test_bot_transcription_client_posts_to_the_transcribe_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_suffix = "/transcribe"
    _result, session = await _transcribe_with_fake_session(monkeypatch)
    url = str(session.posts[0]["url"])
    assert url.endswith(expected_suffix), "the transcription request path differs"


@pytest.mark.asyncio
async def test_bot_transcription_client_sends_the_audio_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_headers = {"Authorization": "Bearer whisper-test-key"}
    _result, session = await _transcribe_with_fake_session(monkeypatch)
    headers = session.options["headers"]
    assert headers == expected_headers, "the transcription headers differ"


def test_shared_document_example_has_the_documented_fields() -> None:
    expected_fields = {"format", "text", "characters", "truncated"}
    payload = CONTRACT["process_document"]
    assert set(payload) == expected_fields, "the document example fields differ"


def test_shared_document_example_passes_the_bot_response_validation() -> None:
    payload = CONTRACT["process_document"]
    validated = validate_document_response(payload)
    assert validated is payload, "the bot rejects the document example"


@pytest.mark.asyncio
async def test_bot_document_client_accepts_shared_audiodoc_example(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_payload = CONTRACT["process_document"]
    result, _session = await _process_with_fake_session(monkeypatch)
    assert result == expected_payload, "the document result differs"


@pytest.mark.asyncio
async def test_bot_document_client_posts_to_the_process_document_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_suffix = "/process-document"
    _result, session = await _process_with_fake_session(monkeypatch)
    url = str(session.posts[0]["url"])
    assert url.endswith(expected_suffix), "the document request path differs"


@pytest.mark.asyncio
async def test_bot_document_client_sends_the_document_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_headers = {"Authorization": "Bearer document-test-key"}
    _result, session = await _process_with_fake_session(monkeypatch)
    headers = session.options["headers"]
    assert headers == expected_headers, "the document headers differ"


@pytest.mark.asyncio
async def test_bot_document_client_sends_the_character_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_max_characters = "11264"
    _result, session = await _process_with_fake_session(monkeypatch)
    fields = form_fields(cast("aiohttp.FormData", session.posts[0]["data"]))
    assert fields["max_characters"][1] == expected_max_characters, (
        "the document character limit differs"
    )


@pytest.mark.parametrize(
    ("path", "example"),
    [("/transcribe", "transcribe"), ("/process-document", "process_document")],
)
def test_shared_audiodoc_response_examples_match_openapi(
    path: str,
    example: str,
) -> None:
    expected_empty: list[str] = []
    success_status = 200
    errors = _response_errors(path, success_status, CONTRACT[example])
    assert errors == expected_empty, f"the {example} example breaks the schema"


async def _record_real_requests() -> tuple[str, object, list[FakeRequest], list[str]]:
    async with FakeAudiodoc() as server:
        settings = _real_client_settings(server)
        text = await transcribe_audio(b"audio", "voice.ogg", settings=settings)
        document = await process_document(b"document", "note.txt", settings=settings)
        keys = [server.whisper_api_key, server.document_api_key]
        return text, document, list(server.requests), keys


async def _real_request(index: int) -> tuple[FakeRequest, str]:
    _text, _document, requests, keys = await _record_real_requests()
    return requests[index], keys[index]


def _authorization_parameters(path: str) -> list[dict[str, Any]]:
    expected_in = "header"
    expected_lower = "authorization"
    return [
        parameter
        for parameter in _operation(path).get("parameters", [])
        if parameter["in"] == expected_in
        and parameter["name"].lower() == expected_lower
    ]


def _request_schema(path: str) -> dict[str, Any]:
    schema: dict[str, Any] = _operation(path)["requestBody"]["content"][
        "multipart/form-data"
    ]["schema"]
    return schema


REAL_REQUESTS = pytest.mark.parametrize(
    ("index", "path"),
    [(0, "/transcribe"), (1, "/process-document")],
)


@pytest.mark.asyncio
async def test_real_bot_transcription_returns_the_shared_example_text() -> None:
    expected_text = CONTRACT["transcribe"]["text"]
    text, _document, _requests, _keys = await _record_real_requests()
    assert text == expected_text, "the real transcription text differs"


@pytest.mark.asyncio
async def test_real_bot_document_processing_returns_the_shared_example() -> None:
    expected_document = CONTRACT["process_document"]
    _text, document, _requests, _keys = await _record_real_requests()
    assert document == expected_document, "the real document result differs"


@pytest.mark.asyncio
async def test_real_bot_sends_one_request_per_call() -> None:
    expected_count = 2
    _text, _document, requests, _keys = await _record_real_requests()
    assert len(requests) == expected_count, "the number of real requests differs"


@pytest.mark.asyncio
async def test_real_bot_requests_match_audiodoc_openapi() -> None:
    expected_paths = ["/transcribe", "/process-document"]
    _text, _document, requests, _keys = await _record_real_requests()
    paths = [request.path for request in requests]
    assert paths == expected_paths, "the real request paths differ"


@REAL_REQUESTS
@pytest.mark.asyncio
async def test_real_bot_request_uses_post(index: int, path: str) -> None:
    expected_method = "POST"
    request, _api_key = await _real_request(index)
    assert request.method == expected_method, f"{path} is not posted"


@REAL_REQUESTS
@pytest.mark.asyncio
async def test_real_bot_request_sends_a_multipart_form(index: int, path: str) -> None:
    expected_content_type = "multipart/form-data"
    request, _api_key = await _real_request(index)
    assert request.content_type == expected_content_type, (
        f"{path} is not sent as a multipart form"
    )


@pytest.mark.parametrize("path", ["/transcribe", "/process-document"])
def test_audiodoc_operation_documents_one_authorization_header(path: str) -> None:
    expected_count = 1
    parameters = _authorization_parameters(path)
    assert len(parameters) == expected_count, f"{path} documents no single header"


@REAL_REQUESTS
@pytest.mark.asyncio
async def test_real_bot_request_sends_the_bearer_key(index: int, path: str) -> None:
    request, api_key = await _real_request(index)
    expected_authorization = f"Bearer {api_key}"
    assert request.authorization == expected_authorization, (
        f"{path} sends the wrong key"
    )


@REAL_REQUESTS
@pytest.mark.asyncio
async def test_real_bot_request_authorization_matches_the_schema(
    index: int, path: str
) -> None:
    expected_empty: list[str] = []
    request, _api_key = await _real_request(index)
    schema = _authorization_parameters(path)[0]["schema"]
    errors = _schema_errors(schema, request.authorization)
    assert errors == expected_empty, f"the {path} authorization breaks the schema"


@REAL_REQUESTS
@pytest.mark.asyncio
async def test_real_bot_request_sends_only_documented_fields(
    index: int, path: str
) -> None:
    request, _api_key = await _real_request(index)
    properties = set(_resolve_schema(_request_schema(path))["properties"])
    assert set(request.fields) <= properties, f"{path} sends undocumented fields"


@REAL_REQUESTS
@pytest.mark.asyncio
async def test_real_bot_request_sends_every_required_field(
    index: int, path: str
) -> None:
    request, _api_key = await _real_request(index)
    required = set(_resolve_schema(_request_schema(path)).get("required", []))
    assert required <= set(request.fields), f"{path} misses a required field"


@REAL_REQUESTS
@pytest.mark.asyncio
async def test_real_bot_request_fields_match_the_schema(index: int, path: str) -> None:
    expected_empty: list[str] = []
    request, _api_key = await _real_request(index)
    payload: dict[str, object] = dict(request.fields)
    limit_field = "max_characters"
    if limit_field in payload:
        payload[limit_field] = int(request.fields[limit_field])
    errors = _schema_errors(_request_schema(path), payload)
    assert errors == expected_empty, f"the {path} fields break the schema"


ERROR_CASES = [
    (path, int(status))
    for path, operations in OPENAPI["paths"].items()
    for status in operations.get("post", {}).get("responses", {})
    if int(status) >= HTTPStatus.BAD_REQUEST
]
TRANSCRIBE_PATH = "/transcribe"


def _endpoint(path: str) -> Endpoint:
    return "transcribe" if path == TRANSCRIBE_PATH else "process-document"


async def _trigger_error(
    path: str, status: int
) -> tuple[Exception, tuple[str, int, dict[str, object]]]:
    endpoint = _endpoint(path)
    error: pytest.ExceptionInfo[Exception]
    async with FakeAudiodoc() as server:
        settings = _real_client_settings(server)
        server.set_behavior(endpoint, FakeResponseOptions(status=status))
        if path == TRANSCRIBE_PATH:
            with pytest.raises(AudiodocAPIError) as error:
                await transcribe_audio(b"audio", "voice.ogg", settings=settings)
        else:
            with pytest.raises(DocumentAPIError) as error:
                await process_document(b"document", "note.txt", settings=settings)
        return error.value, server.responses[-1]


@pytest.mark.parametrize(
    ("path", "status"),
    [case for case in ERROR_CASES if case[0] == TRANSCRIBE_PATH],
)
@pytest.mark.asyncio
async def test_bot_reports_every_documented_transcription_error_status(
    path: str,
    status: int,
) -> None:
    expected_text = f"audiodoc HTTP {status}"
    error, _response = await _trigger_error(path, status)
    assert expected_text in str(error), f"{status} is not reported"


@pytest.mark.parametrize(
    ("path", "status"),
    [case for case in ERROR_CASES if case[0] != TRANSCRIBE_PATH],
)
@pytest.mark.asyncio
async def test_bot_reports_every_documented_document_error_status(
    path: str,
    status: int,
) -> None:
    error, _response = await _trigger_error(path, status)
    assert getattr(error, "status", None) == status, f"{status} is not reported"


@pytest.mark.parametrize(("path", "status"), ERROR_CASES)
@pytest.mark.asyncio
async def test_bot_handles_every_documented_audiodoc_error_status(
    path: str,
    status: int,
) -> None:
    expected_endpoint = _endpoint(path)
    _error, (endpoint, _status, _payload) = await _trigger_error(path, status)
    assert endpoint == expected_endpoint, f"{path} reached the wrong endpoint"


@pytest.mark.parametrize(("path", "status"), ERROR_CASES)
@pytest.mark.asyncio
async def test_fake_audiodoc_answers_with_the_documented_error_status(
    path: str,
    status: int,
) -> None:
    _error, (_endpoint, response_status, _payload) = await _trigger_error(path, status)
    assert response_status == status, f"{path} answered with another status"


@pytest.mark.parametrize(("path", "status"), ERROR_CASES)
@pytest.mark.asyncio
async def test_documented_error_payloads_match_openapi(
    path: str,
    status: int,
) -> None:
    expected_empty: list[str] = []
    _error, (_endpoint, _status, payload) = await _trigger_error(path, status)
    errors = _response_errors(path, status, payload)
    assert errors == expected_empty, f"the {status} payload breaks the schema"
