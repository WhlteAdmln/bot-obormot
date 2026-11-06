"""Проверки интеграции с LLM-серверами без расширений llama.cpp."""

from contextlib import asynccontextmanager

from aiohttp import web
import pytest

from bot.config import config
from bot.services.llm import LLMClient


@asynccontextmanager
async def running_server(app: web.Application):
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


@pytest.fixture
def configure_openai(monkeypatch):
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(config, "LLM_TOKEN_COUNTING", "auto")
    monkeypatch.setattr(config, "LLM_CONTEXT_SIZE", 8192)
    monkeypatch.setattr(config, "LLM_MAX_TOKENS", 128)


def make_openai_only_app():
    requests = []
    app = web.Application()

    async def models(_request):
        requests.append(("GET", "/v1/models"))
        return web.json_response(
            {"object": "list", "data": [{"id": "test-model", "object": "model"}]}
        )

    async def unsupported(request):
        requests.append((request.method, request.path))
        raise web.HTTPNotFound()

    async def chat_completions(request):
        requests.append(("POST", "/v1/chat/completions"))
        payload = await request.json()
        assert payload["model"] == "test-model"
        assert payload["stream"] is True
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        await response.prepare(request)
        await response.write(
            b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        )
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
    configure_openai, monkeypatch
):
    app, requests = make_openai_only_app()
    async with running_server(app) as base_url:
        monkeypatch.setattr(config, "LLM_BASE_URL", f"{base_url}/v1")
        client = LLMClient()
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
async def test_auto_mode_keeps_llamacpp_tokenization_when_available(monkeypatch):
    requests = []
    app = web.Application()

    async def props(_request):
        requests.append(("GET", "/props"))
        return web.json_response({"n_ctx": 4096})

    async def tokenize(request):
        requests.append(("POST", "/tokenize"))
        payload = await request.json()
        count = 2 if payload["content"] == "rendered" else 3
        return web.json_response({"tokens": list(range(count))})

    async def apply_template(_request):
        requests.append(("POST", "/apply-template"))
        return web.json_response({"prompt": "rendered"})

    async def health(_request):
        requests.append(("GET", "/health"))
        return web.json_response({"status": "ok"})

    app.router.add_get("/props", props)
    app.router.add_post("/tokenize", tokenize)
    app.router.add_post("/apply-template", apply_template)
    app.router.add_get("/health", health)

    monkeypatch.setattr(config, "LLM_TOKEN_COUNTING", "auto")
    monkeypatch.setattr(config, "LLM_CONTEXT_SIZE", None)
    monkeypatch.setattr(config, "LLM_BASE_URL", "")
    monkeypatch.setattr(config, "LLM_MODEL", "test-model")

    async with running_server(app) as base_url:
        monkeypatch.setattr(config, "LLM_BASE_URL", f"{base_url}/v1")
        client = LLMClient()
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
