# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Real-wire fake audiodoc server for client tests."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self, TypeAlias

from aiohttp import web
from aiohttp.test_utils import TestServer

if TYPE_CHECKING:
    from types import TracebackType

Endpoint: TypeAlias = Literal["transcribe", "process-document"]

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "contract"
    / "fixtures"
    / "audiodoc_responses.json"
)
_FIXTURE_KEYS: dict[Endpoint, str] = {
    "transcribe": "transcribe",
    "process-document": "process_document",
}
_ERROR_DETAILS = {
    HTTPStatus.BAD_REQUEST: "The uploaded file could not be processed",
    HTTPStatus.UNAUTHORIZED: "Invalid API key",
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "Request body is too large",
    HTTPStatus.UNSUPPORTED_MEDIA_TYPE: "Unsupported media type",
    HTTPStatus.UNPROCESSABLE_ENTITY: "Invalid request",
    HTTPStatus.INTERNAL_SERVER_ERROR: "Unexpected internal failure",
    HTTPStatus.SERVICE_UNAVAILABLE: "Service unavailable",
    HTTPStatus.GATEWAY_TIMEOUT: "Processing timed out",
}
_ERROR_CODES: dict[tuple[Endpoint, HTTPStatus], str] = {
    ("transcribe", HTTPStatus.BAD_REQUEST): "invalid_audio",
    ("process-document", HTTPStatus.BAD_REQUEST): "document_rejected",
    ("transcribe", HTTPStatus.REQUEST_ENTITY_TOO_LARGE): "payload_too_large",
    ("process-document", HTTPStatus.REQUEST_ENTITY_TOO_LARGE): "payload_too_large",
    ("transcribe", HTTPStatus.INTERNAL_SERVER_ERROR): "internal_error",
    ("process-document", HTTPStatus.INTERNAL_SERVER_ERROR): "internal_error",
    ("transcribe", HTTPStatus.SERVICE_UNAVAILABLE): "server_busy",
    ("process-document", HTTPStatus.SERVICE_UNAVAILABLE): "server_busy",
    ("transcribe", HTTPStatus.GATEWAY_TIMEOUT): "transcription_timeout",
    ("process-document", HTTPStatus.GATEWAY_TIMEOUT): "processing_timeout",
}
_SUPPORTED_STATUSES = {HTTPStatus.OK, *_ERROR_DETAILS}


@dataclass(frozen=True, slots=True)
class FakeRequest:
    """Record the request received by the fake server."""

    method: str
    path: str
    content_type: str
    authorization: str | None
    fields: dict[str, str]


@dataclass(frozen=True, slots=True)
class FakeResponseOptions:
    """Configure one audiodoc endpoint response."""

    status: int = HTTPStatus.OK
    delay: float = 0.0
    truncated_body: bool = False
    invalid_json: bool = False
    retry_after_seconds: int = 5

    def __post_init__(self) -> None:
        """Validate response options."""
        if self.status not in _SUPPORTED_STATUSES:
            msg = "Unsupported fake audiodoc status"
            raise ValueError(msg)
        if self.delay < 0:
            msg = "Response delay cannot be negative"
            raise ValueError(msg)
        if self.retry_after_seconds < 0:
            msg = "Retry-After cannot be negative"
            raise ValueError(msg)


def _load_responses() -> dict[Endpoint, dict[str, object]]:
    """Load and validate the shared audiodoc response examples."""
    fixture: object = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict):
        msg = "Invalid audiodoc response fixture"
        raise TypeError(msg)

    responses: dict[Endpoint, dict[str, object]] = {}
    for endpoint, fixture_key in _FIXTURE_KEYS.items():
        payload = fixture.get(fixture_key)
        if not isinstance(payload, dict):
            msg = f"Missing audiodoc fixture response: {fixture_key}"
            raise TypeError(msg)
        responses[endpoint] = payload

    return responses


class FakeAudiodoc:
    """Run an aiohttp audiodoc-compatible server on a random local port."""

    def __init__(
        self,
        *,
        whisper_api_key: str = "whisper-test-key",
        document_api_key: str = "document-test-key",
    ) -> None:
        """Create the fake application and its response controls."""
        self.whisper_api_key = whisper_api_key
        self.document_api_key = document_api_key
        self._payloads = _load_responses()
        self._behaviors: dict[Endpoint, FakeResponseOptions] = {
            "transcribe": FakeResponseOptions(),
            "process-document": FakeResponseOptions(),
        }
        self.requests: list[FakeRequest] = []
        self.responses: list[tuple[Endpoint, int, dict[str, object]]] = []

        self.app = web.Application()
        self.app.router.add_get("/health", self._health)
        self.app.router.add_get("/ready", self._ready)
        self.app.router.add_post("/transcribe", self._transcribe)
        self.app.router.add_post("/process-document", self._process_document)
        self.server = TestServer(self.app)

    @property
    def base_url(self) -> str:
        """Return the server URL after it has been started."""
        return str(self.server.make_url("/"))

    def set_behavior(
        self,
        endpoint: Endpoint,
        options: FakeResponseOptions,
    ) -> None:
        """Set response behavior for one API endpoint."""
        self._behaviors[endpoint] = options

    async def __aenter__(self) -> Self:
        """Start the server and return this support object."""
        await self.server.start_server()
        return self

    async def __aexit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Stop the server and release its listening socket."""
        await self.server.close()

    async def _health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _ready(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ready"})

    async def _transcribe(self, request: web.Request) -> web.StreamResponse:
        return await self._respond(
            request,
            "transcribe",
            self.whisper_api_key,
        )

    async def _process_document(
        self,
        request: web.Request,
    ) -> web.StreamResponse:
        return await self._respond(
            request,
            "process-document",
            self.document_api_key,
        )

    async def _respond(
        self,
        request: web.Request,
        endpoint: Endpoint,
        api_key: str,
    ) -> web.StreamResponse:
        if api_key and request.headers.get("Authorization") != f"Bearer {api_key}":
            return web.json_response(
                {"detail": "Invalid API key"},
                status=HTTPStatus.UNAUTHORIZED,
            )

        form = await request.post()
        try:
            self.requests.append(
                FakeRequest(
                    method=request.method,
                    path=request.path,
                    content_type=request.content_type,
                    authorization=request.headers.get("Authorization"),
                    fields={
                        name: (
                            value.filename
                            if isinstance(value, web.FileField)
                            else str(value)
                        )
                        for name, value in form.items()
                    },
                )
            )
            if "file" not in form:
                return web.json_response(
                    {"detail": "Missing file field"},
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                )

            behavior = self._behaviors[endpoint]
            if behavior.delay:
                await asyncio.sleep(behavior.delay)

            return await self._create_response(request, endpoint, behavior)
        finally:
            for value in form.values():
                if isinstance(value, web.FileField):
                    value.file.close()

    async def _create_response(
        self,
        request: web.Request,
        endpoint: Endpoint,
        behavior: FakeResponseOptions,
    ) -> web.StreamResponse:
        if behavior.status != HTTPStatus.OK:
            return self._error_response(endpoint, behavior)

        body = json.dumps(self._payloads[endpoint]).encode("utf-8")
        if behavior.invalid_json:
            body = b"{invalid-json"

        if behavior.truncated_body:
            return await self._truncated_response(request, body)

        return web.Response(body=body, content_type="application/json")

    def _error_response(
        self,
        endpoint: Endpoint,
        behavior: FakeResponseOptions,
    ) -> web.Response:
        status = HTTPStatus(behavior.status)
        if status == HTTPStatus.UNPROCESSABLE_ENTITY:
            payload: dict[str, object] = {
                "detail": [
                    {
                        "loc": ["body", "file"],
                        "msg": "Field required",
                        "type": "missing",
                    }
                ]
            }
        else:
            payload = {"detail": _ERROR_DETAILS[status]}
            code = _ERROR_CODES.get((endpoint, status))
            if code is not None:
                payload["code"] = code

        self.responses.append((endpoint, behavior.status, payload))
        headers = {}
        if status == HTTPStatus.SERVICE_UNAVAILABLE:
            headers["Retry-After"] = str(behavior.retry_after_seconds)
        return web.json_response(
            payload,
            status=behavior.status,
            headers=headers,
        )

    async def _truncated_response(
        self,
        request: web.Request,
        body: bytes,
    ) -> web.StreamResponse:
        response = web.StreamResponse(
            status=HTTPStatus.OK,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body) + 1),
                "Connection": "close",
            },
        )
        response.force_close()
        await response.prepare(request)
        await response.write(body[: max(1, len(body) // 2)])
        await response.write_eof()
        transport = request.transport
        if transport is not None:
            transport.close()
        return response
