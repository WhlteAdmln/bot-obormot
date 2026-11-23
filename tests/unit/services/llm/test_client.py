# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm client."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from aiohttp import web

from bot_obormot.services.llm import LLMClient
from bot_obormot.settings import Settings
from tests.support.llm_context_tokenizer import FakeResponse, FakeSession, make_client


@asynccontextmanager
async def running_server(app: web.Application) -> AsyncIterator[str]:
    """Running server."""
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets
    port = sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


def _with_token_counting(settings: Settings, mode: str) -> Settings:
    """Return settings with the requested token counting mode."""
    changes = {"LLM_TOKEN_COUNTING": mode}
    return replace(settings, **changes)


@pytest.fixture
def openai_settings() -> Settings:
    """Build settings for the OpenAI-compatible test server."""
    return _with_token_counting(
        replace(
            Settings(),
            LLM_MODEL="test-model",
            LLM_API_KEY="",
            LLM_CONTEXT_SIZE=8192,
            LLM_MAX_TOKENS=128,
        ),
        "auto",
    )


def make_openai_only_app() -> tuple[object, ...]:
    """Make openai only app."""
    requests = []
    app = web.Application()

    async def models(_request: web.Request) -> web.Response:
        requests.append(("GET", "/v1/models"))
        return web.json_response(
            {"object": "list", "data": [{"id": "test-model", "object": "model"}]}
        )

    async def unsupported(request: web.Request) -> None:
        requests.append((request.method, request.path))
        raise web.HTTPNotFound

    async def chat_completions(request: web.Request) -> web.StreamResponse:
        requests.append(("POST", "/v1/chat/completions"))
        payload = await request.json()
        assert payload["model"] == "test-model"
        assert payload["stream"] is True
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        await response.prepare(request)
        await response.write(b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n')
        await response.write(
            b'data: {"choices":[{"delta":{"content":", world!"}}]}\n\n'
        )
        await response.write(b"data: [DONE]\n\n")
        await response.write_eof()
        return response

    app.router.add_get("/v1/models", models)
    app.router.add_get("/health", unsupported)
    app.router.add_get("/props", unsupported)
    app.router.add_post("/tokenize", unsupported)
    app.router.add_post("/apply-template", unsupported)
    app.router.add_post("/v1/chat/completions", chat_completions)
    return app, requests


@pytest.mark.asyncio
async def test_openai_compatible_server_works_without_llama_endpoints(
    openai_settings: Settings,
) -> None:
    """Openai compatible server works without llama endpoints."""
    app, requests = make_openai_only_app()
    async with running_server(app) as base_url:
        settings = replace(openai_settings, LLM_BASE_URL=f"{base_url}/v1")
        client = LLMClient(settings=settings)
        try:
            assert await client.get_context_size() == 8192
            assert await client.get_token_counting_mode() == "estimate"
            assert await client.count_text_tokens("Привет") == 2

            messages = await client.fit_messages_to_context(
                "system prompt",
                [
                    {"role": "user", "content": "previous question"},
                    {"role": "assistant", "content": "previous answer"},
                ],
                "current question",
            )
            assert [message["role"] for message in messages] == [
                "system",
                "user",
                "assistant",
                "user",
            ]

            response = "".join([chunk async for chunk in client.stream(messages)])
            assert response == "Hello, world!"
            assert await client.health_check() == (True, "Доступен")
        finally:
            await client.close()

    # The only generation endpoint used is the standard OpenAI-compatible one.
    assert ("POST", "/v1/chat/completions") in requests
    assert ("GET", "/v1/models") in requests
    assert ("POST", "/tokenize") in requests  # one best-effort capability probe
    assert ("POST", "/apply-template") not in requests
    assert ("GET", "/props") not in requests  # explicit LLM_CONTEXT_SIZE wins


@pytest.mark.asyncio
async def test_auto_mode_keeps_llamacpp_tokenization_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto mode keeps llamacpp tokenization when available."""
    requests = []
    app = web.Application()

    async def props(_request: web.Request) -> web.Response:
        requests.append(("GET", "/props"))
        return web.json_response({"n_ctx": 4096})

    async def tokenize(request: web.Request) -> web.Response:
        requests.append(("POST", "/tokenize"))
        payload = await request.json()
        count = 2 if payload["content"] == "rendered" else 3
        return web.json_response({"tokens": list(range(count))})

    async def apply_template(_request: web.Request) -> web.Response:
        requests.append(("POST", "/apply-template"))
        return web.json_response({"prompt": "rendered"})

    async def health(_request: web.Request) -> web.Response:
        requests.append(("GET", "/health"))
        return web.json_response({"status": "ok"})

    app.router.add_get("/props", props)
    app.router.add_post("/tokenize", tokenize)
    app.router.add_post("/apply-template", apply_template)
    app.router.add_get("/health", health)

    settings = _with_token_counting(
        replace(
            Settings(),
            LLM_CONTEXT_SIZE=None,
            LLM_BASE_URL="",
            LLM_MODEL="test-model",
        ),
        "auto",
    )

    async with running_server(app) as base_url:
        settings = replace(settings, LLM_BASE_URL=f"{base_url}/v1")
        client = LLMClient(settings=settings)
        monkeypatch.setattr(client, "_server_url", lambda: base_url)
        try:
            assert await client.get_context_size() == 4096
            assert await client.count_tokens([{"role": "user", "content": "hi"}]) == 2
            assert await client.get_token_counting_mode() == "llamacpp"
            assert await client.health_check() == (True, "Доступен")
        finally:
            await client.close()

    assert requests.count(("POST", "/tokenize")) == 2
    assert ("POST", "/apply-template") in requests


@pytest.mark.asyncio
async def test_health_check_does_not_return_raw_unexpected_server_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Health check does not return raw unexpected server payload."""
    payload = {"status": "error", "details": "private prompt content"}
    fake_session = FakeSession([FakeResponse(payload), FakeResponse({"data": []})])
    client = make_client(monkeypatch, fake_session)

    result = await client.health_check()

    assert result == (True, "Доступен")
    assert "private prompt content" not in result[1]


def test_llm_client_exposes_public_methods() -> None:
    """LLM client exposes its public methods."""
    client = LLMClient()
    assert callable(client.count_tokens)
    assert callable(client.fit_messages_to_context)
    assert callable(client.stream)


def test_client_resolves_process_settings_lazily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolve process settings only when the client first needs them."""
    settings = replace(Settings(), LLM_BASE_URL="http://localhost:8080/v1")
    calls = 0

    def load_settings() -> Settings:
        nonlocal calls
        calls += 1
        return settings

    monkeypatch.setattr("bot_obormot.services.llm.client.get_settings", load_settings)
    client = LLMClient()

    assert calls == 0
    assert client.get_server_url() == "http://localhost:8080"
    assert calls == 1


def test_client_exposes_message_normalization_and_counting_helpers() -> None:
    """Expose message helpers through the public client methods."""
    client = LLMClient()
    source = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,x"}},
            ],
        }
    ]

    assert client._normalize_content(None) == ""
    normalized = client.normalize_messages(source)
    assert client._normalize_messages(source) == normalized
    prepared = client.prepare_messages_for_count(normalized)
    assert client._prepare_messages_for_count(normalized) == prepared
    assert client.count_images(normalized) == 1
    assert client._count_images(normalized) == 1


@pytest.mark.asyncio
async def test_close_without_open_session_is_safe() -> None:
    """Close a client that has never opened an HTTP session."""
    client = LLMClient()

    await client.close()

    assert client.session is None
