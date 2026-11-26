# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm client."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from bot_obormot.services.llm import LLMClient
from bot_obormot.services.llm.messages import prepare_messages_for_count
from bot_obormot.settings import Settings
from tests.support.fake_llm import open_llm_client
from tests.support.llm_context_tokenizer import FakeResponse, FakeSession, make_client


@asynccontextmanager
async def running_server(app: web.Application) -> AsyncIterator[str]:
    """Running server."""
    async with TestServer(app, host="127.0.0.1") as server:
        yield f"http://127.0.0.1:{server.port}"


def _with_token_counting(settings: Settings, mode: str) -> Settings:
    """Return settings with the requested token counting mode."""
    return replace(settings, LLM_TOKEN_COUNTING=mode)


@pytest.fixture(name="openai_settings")
def fixture_openai_settings() -> Settings:
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


def make_openai_only_app() -> tuple[
    web.Application, list[tuple[str, str]], list[dict[str, object]]
]:
    """Make an OpenAI-only app that records requests and chat payloads."""
    requests: list[tuple[str, str]] = []
    payloads: list[dict[str, object]] = []
    app = web.Application()

    async def models(_request: web.Request) -> web.Response:
        requests.append(("GET", "/v1/models"))
        return web.json_response(
            {"object": "list", "data": [{"id": "test-model", "object": "model"}]}
        )

    async def unsupported(request: web.Request) -> web.Response:
        requests.append((request.method, request.path))
        raise web.HTTPNotFound

    async def chat_completions(request: web.Request) -> web.StreamResponse:
        requests.append(("POST", "/v1/chat/completions"))
        payloads.append(await request.json())
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
    return app, requests, payloads


async def _run_openai_scenario(
    openai_settings: Settings,
) -> tuple[dict[str, object], list[tuple[str, str]], list[dict[str, object]]]:
    """Run every client call against the OpenAI-only server."""
    app, requests, payloads = make_openai_only_app()
    results: dict[str, object] = {}
    async with running_server(app) as base_url:
        settings = replace(openai_settings, LLM_BASE_URL=f"{base_url}/v1")
        async with open_llm_client(settings) as client:
            results["context_size"] = await client.get_context_size()
            results["mode"] = await client.get_token_counting_mode()
            results["text_tokens"] = await client.count_text_tokens("Привет")
            messages = await client.fit_messages_to_context(
                "system prompt",
                [
                    {"role": "user", "content": "previous question"},
                    {"role": "assistant", "content": "previous answer"},
                ],
                "current question",
            )
            results["roles"] = [message["role"] for message in messages]
            chunks = [chunk async for chunk in client.stream(messages)]
            results["response"] = "".join(chunks)
            results["health"] = await client.health_check()
    return results, requests, payloads


def make_llamacpp_app() -> tuple[web.Application, list[tuple[str, str]]]:
    """Make a llama.cpp app that records requests."""
    requests: list[tuple[str, str]] = []
    app = web.Application()

    async def props(_request: web.Request) -> web.Response:
        requests.append(("GET", "/props"))
        return web.json_response({"n_ctx": 4096})

    async def tokenize(request: web.Request) -> web.Response:
        requests.append(("POST", "/tokenize"))
        payload = await request.json()
        rendered_prompt = "rendered"
        count = 2 if payload["content"] == rendered_prompt else 3
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
    return app, requests


async def _run_llamacpp_scenario() -> tuple[dict[str, object], list[tuple[str, str]]]:
    """Run the auto-mode client calls against the llama.cpp server."""
    app, requests = make_llamacpp_app()
    settings = _with_token_counting(
        replace(Settings(), LLM_CONTEXT_SIZE=None, LLM_MODEL="test-model"), "auto"
    )
    results: dict[str, object] = {}
    async with running_server(app) as base_url:
        settings = replace(settings, LLM_BASE_URL=f"{base_url}/v1")
        async with open_llm_client(settings) as client:
            results["context_size"] = await client.get_context_size()
            results["tokens"] = await client.count_tokens(
                [{"role": "user", "content": "hi"}]
            )
            results["mode"] = await client.get_token_counting_mode()
            results["health"] = await client.health_check()
    return results, requests


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("context_size", 8192),
        ("mode", "estimate"),
        ("text_tokens", 2),
        ("roles", ["system", "user", "assistant", "user"]),
        ("response", "Hello, world!"),
        ("health", (True, "Доступен")),
    ],
)
async def test_openai_compatible_server_works_without_llama_endpoints(
    openai_settings: Settings, key: str, expected: object
) -> None:
    results, _requests, _payloads = await _run_openai_scenario(openai_settings)
    assert results[key] == expected, f"{key} is wrong on an OpenAI-only server"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_line",
    [("POST", "/v1/chat/completions"), ("GET", "/v1/models"), ("POST", "/tokenize")],
)
async def test_openai_compatible_server_receives_the_expected_requests(
    openai_settings: Settings, request_line: tuple[str, str]
) -> None:
    _results, requests, _payloads = await _run_openai_scenario(openai_settings)
    assert request_line in requests, f"{request_line} was not requested"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_line", [("POST", "/apply-template"), ("GET", "/props")]
)
async def test_openai_compatible_server_skips_llama_only_requests(
    openai_settings: Settings, request_line: tuple[str, str]
) -> None:
    _results, requests, _payloads = await _run_openai_scenario(openai_settings)
    assert request_line not in requests, f"{request_line} was requested"


@pytest.mark.asyncio
async def test_openai_compatible_stream_sends_the_configured_model(
    openai_settings: Settings,
) -> None:
    expected_model = "test-model"
    _results, _requests, payloads = await _run_openai_scenario(openai_settings)
    (payload,) = payloads
    assert payload["model"] == expected_model, "the stream used another model"


@pytest.mark.asyncio
async def test_openai_compatible_stream_requests_streaming(
    openai_settings: Settings,
) -> None:
    _results, _requests, payloads = await _run_openai_scenario(openai_settings)
    (payload,) = payloads
    assert payload["stream"] is True, "the chat request is not streaming"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("context_size", 4096),
        ("tokens", 2),
        ("mode", "llamacpp"),
        ("health", (True, "Доступен")),
    ],
)
async def test_auto_mode_keeps_llamacpp_tokenization_when_available(
    key: str, expected: object
) -> None:
    results, _requests = await _run_llamacpp_scenario()
    assert results[key] == expected, f"{key} is wrong on a llama.cpp server"


@pytest.mark.asyncio
async def test_auto_mode_tokenizes_twice_on_a_llamacpp_server() -> None:
    expected_count = 2
    _results, requests = await _run_llamacpp_scenario()
    tokenize_count = requests.count(("POST", "/tokenize"))
    assert tokenize_count == expected_count, "the tokenize count is wrong"


@pytest.mark.asyncio
async def test_auto_mode_applies_the_llamacpp_chat_template() -> None:
    request_line = ("POST", "/apply-template")
    _results, requests = await _run_llamacpp_scenario()
    assert request_line in requests, "the chat template was not applied"


@pytest.mark.asyncio
async def test_health_check_reports_available_for_unexpected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"status": "error", "details": "private prompt content"}
    fake_session = FakeSession([FakeResponse(payload), FakeResponse({"data": []})])
    client = make_client(monkeypatch, fake_session)
    expected_result = (True, "Доступен")

    result = await client.health_check()

    assert result == expected_result, "the health check result is wrong"


@pytest.mark.asyncio
async def test_health_check_does_not_return_raw_unexpected_server_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt_text = "secret user draft 42"
    payload = {"status": "failed", "details": prompt_text}
    fake_session = FakeSession([FakeResponse(payload), FakeResponse({"data": []})])
    client = make_client(monkeypatch, fake_session)

    _available, message = await client.health_check()

    assert prompt_text not in message, "the raw server payload leaked"


@pytest.mark.parametrize("name", ["count_tokens", "fit_messages_to_context", "stream"])
def test_llm_client_exposes_public_methods(name: str) -> None:
    client = LLMClient()
    assert callable(getattr(client, name)), f"{name} is not a public method"


def _counting_loader(monkeypatch: pytest.MonkeyPatch, base_url: str) -> list[Settings]:
    """Patch the settings loader and return the list of its results."""
    settings = replace(Settings(), LLM_BASE_URL=base_url)
    calls: list[Settings] = []

    def load_settings() -> Settings:
        calls.append(settings)
        return settings

    monkeypatch.setattr("bot_obormot.services.llm.client.get_settings", load_settings)
    return calls


def test_client_does_not_load_settings_on_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _counting_loader(monkeypatch, "http://localhost:8080/v1")
    LLMClient()
    expected_empty: list[Settings] = []
    assert calls == expected_empty, "the settings were loaded eagerly"


def test_client_resolves_the_server_url_from_process_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _counting_loader(monkeypatch, "http://10.1.2.3:9191/v1")
    client = LLMClient()
    expected_server_url = "http://10.1.2.3:9191"
    assert client.get_server_url() == expected_server_url, "the server URL is wrong"


def test_client_loads_process_settings_once_on_first_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _counting_loader(monkeypatch, "http://llm.local:8000/v1")
    client = LLMClient()
    client.get_server_url()
    expected_count = 1
    assert len(calls) == expected_count, "the settings were not loaded exactly once"


def test_client_exposes_message_normalization_and_counting_helpers() -> None:
    client = LLMClient()
    source = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Что на фото?"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,x"}},
            ],
        }
    ]

    normalized = client.normalize_messages(source)
    assert client.count_images(normalized) == 1, "one image part is expected"


@pytest.mark.asyncio
async def test_close_without_open_session_is_safe() -> None:
    client = LLMClient()

    await client.close()

    assert client.session is None, "close opened a session"


def test_client_prepares_messages_like_the_messages_module() -> None:
    normalized = [{"role": "user", "content": [{"type": "text", "text": "Ёлка"}]}]
    expected = prepare_messages_for_count(normalized)
    actual = LLMClient().prepare_messages_for_count(normalized)
    assert actual == expected, "the client must delegate token-count preparation"
