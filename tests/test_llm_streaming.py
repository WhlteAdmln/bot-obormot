import logging

import aiohttp
import pytest

from bot.config import config
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.services.llm import LLMClient
from bot.services.llm import client as client_module
from bot.services.llm.streaming import stream_unlimited


class AsyncLines:
    def __init__(self, lines):
        self.lines = iter(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.lines)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeResponse:
    def __init__(self, lines=(), status=200, body=""):
        self.content = AsyncLines(lines)
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def text(self):
        return self.body


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


async def collect(stream):
    return [chunk async for chunk in stream]


@pytest.mark.asyncio
async def test_stream_unlimited_yields_content_and_ignores_non_content_chunks(
    monkeypatch,
):
    response = FakeResponse(
        [
            b"event: message\n",
            b'data: {"choices": []}\n',
            b"data: not-json\n",
            b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
            'data: {"choices":[{"delta":{"content":"Привет"}}]}\n'.encode(),
            b'data: {"choices":[{"delta":{"content":"!"}}]}\n',
            b"data: [DONE]\n",
            'data: {"choices":[{"delta":{"content":"после DONE"}}]}\n'.encode(),
        ]
    )
    session = FakeSession(response)
    client = LLMClient()

    async def get_session():
        return session

    normalized = []

    def normalize(messages):
        normalized.append(messages)
        return [{"role": "user", "content": "normalized"}]

    monkeypatch.setattr(client, "_get_session", get_session)
    monkeypatch.setattr(client, "_normalize_messages", normalize)

    result = await collect(
        stream_unlimited(client, [{"role": "user", "content": "raw"}])
    )

    assert result == ["Привет", "!"]
    assert normalized == [[{"role": "user", "content": "raw"}]]
    assert session.calls == [
        (
            f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions",
            {
                "json": {
                    "model": config.LLM_MODEL,
                    "messages": [{"role": "user", "content": "normalized"}],
                    "temperature": config.LLM_TEMPERATURE,
                    "top_p": config.LLM_TOP_P,
                    "max_tokens": config.LLM_MAX_TOKENS,
                    "stream": True,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_stream_unlimited_raises_api_error_with_response_details(
    monkeypatch, caplog
):
    private_detail = "prompt fragment\nsecond line"
    session = FakeSession(FakeResponse(status=503, body=private_detail))
    client = LLMClient()

    async def get_session():
        return session

    monkeypatch.setattr(client, "_get_session", get_session)

    with caplog.at_level(logging.ERROR, logger="bot.services.llm.streaming"):
        with pytest.raises(LLMAPIError) as error:
            await collect(stream_unlimited(client, []))

    assert error.value.status == 503
    assert error.value.detail == private_detail
    assert r"prompt fragment\nsecond line" in caplog.text
    assert "prompt fragment\nsecond line" not in caplog.text


@pytest.mark.asyncio
async def test_stream_unlimited_converts_timeout(monkeypatch):
    client = LLMClient()

    async def get_session():
        raise TimeoutError

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMTimeoutError, match="timed out"):
        await collect(stream_unlimited(client, []))


@pytest.mark.asyncio
async def test_stream_unlimited_converts_aiohttp_client_error(monkeypatch):
    client = LLMClient()

    async def get_session():
        raise aiohttp.ClientConnectionError("connection refused")

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMUnavailableError, match="Could not connect"):
        await collect(stream_unlimited(client, []))


@pytest.mark.asyncio
async def test_llm_client_unlimited_stream_delegates(monkeypatch):
    client = LLMClient()
    messages = [{"role": "user", "content": "hello"}]
    calls = []

    async def fake_stream(client_arg, messages_arg):
        calls.append((client_arg, messages_arg))
        yield "hello"
        yield " world"

    monkeypatch.setattr(client_module, "stream_unlimited", fake_stream)

    assert await collect(client._stream_unlimited(messages)) == ["hello", " world"]
    assert calls == [(client, messages)]


@pytest.mark.asyncio
async def test_public_stream_keeps_semaphore_wrapping_unlimited_stream(monkeypatch):
    client = LLMClient()
    messages = [{"role": "user", "content": "hello"}]
    calls = []

    async def fake_stream(self, received_messages):
        calls.append((self, received_messages))
        yield "token"

    monkeypatch.setattr(client, "_stream_unlimited", fake_stream.__get__(client))

    assert await collect(client.stream(messages)) == ["token"]
    assert calls == [(client, messages)]
