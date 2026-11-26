# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Real-wire fake OpenAI-compatible LLM server for client tests."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, NamedTuple, Self

from aiohttp import web
from aiohttp.test_utils import TestServer

from bot_obormot.services.llm import LLMClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

    from bot_obormot.settings import Settings

_SUPPORTED_CHAT_STATUSES = {
    HTTPStatus.OK,
    HTTPStatus.UNAUTHORIZED,
    HTTPStatus.TOO_MANY_REQUESTS,
    HTTPStatus.INTERNAL_SERVER_ERROR,
}


class _ChatError(NamedTuple):
    detail: str
    error_type: str


_CHAT_ERRORS = {
    HTTPStatus.UNAUTHORIZED: _ChatError("Invalid API key", "authentication_error"),
    HTTPStatus.TOO_MANY_REQUESTS: _ChatError("Rate limit exceeded", "rate_limit_error"),
    HTTPStatus.INTERNAL_SERVER_ERROR: _ChatError(
        "Internal server error", "server_error"
    ),
}
_DONE = b"data: [DONE]\n\n"


@dataclass(frozen=True, slots=True)
class FakeChatOptions:
    """Configure chat completion responses and failures of the fake LLM server."""

    status: int = HTTPStatus.OK
    first_token_delay: float = 0.0
    drop_after_chunks: int | None = None
    chunks: tuple[str, ...] = ("Hello", ", world!")

    def __post_init__(self) -> None:
        """Validate fake chat options."""
        if self.status not in _SUPPORTED_CHAT_STATUSES:
            msg = "Unsupported fake LLM chat status"
            raise ValueError(msg)
        if self.first_token_delay < 0:
            msg = "First token delay cannot be negative"
            raise ValueError(msg)
        if self.drop_after_chunks is not None and self.drop_after_chunks < 1:
            msg = "Drop position must be positive"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class FakeTokenizerOptions:
    """Configure tokenizer and template responses of the fake LLM server."""

    available: bool = True
    tokenize_status: int = HTTPStatus.OK
    tokenize_delay: float = 0.0
    apply_template_status: int = HTTPStatus.OK

    def __post_init__(self) -> None:
        """Validate fake tokenizer options."""
        if self.tokenize_delay < 0:
            msg = "Tokenizer delay cannot be negative"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class FakeLLMOptions:
    """Configure responses and failures of the fake LLM server."""

    chat: FakeChatOptions = field(default_factory=FakeChatOptions)
    tokenizer: FakeTokenizerOptions = field(default_factory=FakeTokenizerOptions)
    include_context_metadata: bool = True
    context_size: int = 8192

    def __post_init__(self) -> None:
        """Validate fake model options."""
        if self.context_size <= 0:
            msg = "Context size must be positive"
            raise ValueError(msg)


class FakeLLM:
    """Run an OpenAI-compatible LLM server on a random local port."""

    def __init__(
        self,
        *,
        model: str = "test-model",
        api_key: str | None = "test-key",
        options: FakeLLMOptions | None = None,
    ) -> None:
        """Create the fake application and its response controls."""
        self.model = model
        self.api_key = api_key
        self.options = options or FakeLLMOptions()
        self.stream_started = asyncio.Event()
        self.chat_requests: list[dict[str, Any]] = []

        self.app = web.Application()
        self.app.router.add_get("/health", self._health)
        self.app.router.add_get("/props", self._props)
        self.app.router.add_get("/v1/models", self._models)
        self.app.router.add_post("/v1/chat/completions", self._chat_completions)
        self.app.router.add_post("/tokenize", self._tokenize)
        self.app.router.add_post("/apply-template", self._apply_template)
        self.server = TestServer(self.app)

    @property
    def base_url(self) -> str:
        """Return the server root URL after startup."""
        return str(self.server.make_url("/"))

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

    def _authorization_error(self, request: web.Request) -> web.Response | None:
        if self.api_key is None or not self.api_key:
            return None
        if request.headers.get("Authorization") == f"Bearer {self.api_key}":
            return None
        return web.json_response(
            {
                "error": {
                    "message": "Invalid API key",
                    "type": "authentication_error",
                    "code": "invalid_api_key",
                }
            },
            status=HTTPStatus.UNAUTHORIZED,
        )

    async def _health(self, request: web.Request) -> web.Response:
        error = self._authorization_error(request)
        if error is not None:
            return error
        return web.json_response({"status": "ok"})

    async def _props(self, request: web.Request) -> web.Response:
        error = self._authorization_error(request)
        if error is not None:
            return error
        return web.json_response(
            {"error": "Optional llama.cpp props endpoint unavailable"},
            status=HTTPStatus.NOT_FOUND,
        )

    async def _models(self, request: web.Request) -> web.Response:
        error = self._authorization_error(request)
        if error is not None:
            return error

        model_data: dict[str, object] = {
            "id": self.model,
            "object": "model",
            "owned_by": "test",
        }
        if self.options.include_context_metadata:
            model_data["max_model_len"] = self.options.context_size

        return web.json_response({"object": "list", "data": [model_data]})

    async def _chat_completions(
        self,
        request: web.Request,
    ) -> web.StreamResponse:
        error = self._authorization_error(request)
        if error is not None:
            return error

        status = self.options.chat.status
        if status != HTTPStatus.OK:
            detail, error_type = _CHAT_ERRORS[HTTPStatus(status)]
            return web.json_response(
                {"error": {"message": detail, "type": error_type}},
                status=status,
            )

        payload: object = await request.json()
        if isinstance(payload, dict):
            self.chat_requests.append(payload)
        if isinstance(payload, dict) and payload.get("stream") is True:
            return await self._stream_response(request)

        content = "".join(self.options.chat.chunks)
        return web.json_response(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "model": self.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": len(self.options.chat.chunks),
                    "total_tokens": len(self.options.chat.chunks),
                },
            }
        )

    async def _stream_response(
        self,
        request: web.Request,
    ) -> web.StreamResponse:
        events = [
            (
                "data: "
                + json.dumps(
                    {
                        "id": "chatcmpl-test",
                        "object": "chat.completion.chunk",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": content},
                                "finish_reason": None,
                            }
                        ],
                    },
                    separators=(",", ":"),
                )
                + "\n\n"
            ).encode("utf-8")
            for content in self.options.chat.chunks
        ]

        drop_after = self.options.chat.drop_after_chunks
        will_drop = drop_after is not None and drop_after <= len(events)
        headers = {"Content-Type": "text/event-stream"}
        if will_drop:
            headers["Content-Length"] = str(
                sum(len(event) for event in events) + len(_DONE) + 1
            )
            headers["Connection"] = "close"

        response = web.StreamResponse(headers=headers)
        if will_drop:
            response.force_close()
        await response.prepare(request)
        self.stream_started.set()

        for index, event in enumerate(events, start=1):
            if index == 1 and self.options.chat.first_token_delay:
                await asyncio.sleep(self.options.chat.first_token_delay)
            try:
                await response.write(event)
            except ConnectionResetError:
                return response

            if will_drop and index == drop_after:
                transport = request.transport
                if transport is not None:
                    transport.close()
                return response

        await response.write(_DONE)
        await response.write_eof()
        return response

    async def _tokenize(self, request: web.Request) -> web.Response:
        error = self._authorization_error(request)
        if error is not None:
            return error
        if not self.options.tokenizer.available:
            return web.json_response(
                {"error": "Tokenizer unavailable"},
                status=HTTPStatus.NOT_FOUND,
            )

        if self.options.tokenizer.tokenize_delay:
            await asyncio.sleep(self.options.tokenizer.tokenize_delay)
        if self.options.tokenizer.tokenize_status != HTTPStatus.OK:
            return web.json_response(
                {"error": "Tokenizer request failed"},
                status=self.options.tokenizer.tokenize_status,
            )

        payload: object = await request.json()
        content = payload.get("content", "") if isinstance(payload, dict) else ""
        if not isinstance(content, str):
            content = ""
        tokens = list(range(len(content.split())))
        return web.json_response({"tokens": tokens})

    async def _apply_template(self, request: web.Request) -> web.Response:
        error = self._authorization_error(request)
        if error is not None:
            return error
        if self.options.tokenizer.apply_template_status != HTTPStatus.OK:
            return web.json_response(
                {"error": "Template application failed"},
                status=self.options.tokenizer.apply_template_status,
            )

        payload: object = await request.json()
        messages = payload.get("messages", []) if isinstance(payload, dict) else []
        parts: list[str] = []
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, dict):
                    content = message.get("content", "")
                    if isinstance(content, str):
                        parts.append(content)
        return web.json_response({"prompt": "\n".join(parts)})


@asynccontextmanager
async def open_llm_client(settings: Settings | None = None) -> AsyncIterator[LLMClient]:
    """Create a real LLM client and close it when the block ends."""
    client = LLMClient(settings=settings)
    try:
        yield client
    finally:
        await client.close()
