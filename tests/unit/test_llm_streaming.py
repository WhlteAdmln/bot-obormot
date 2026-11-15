# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm streaming."""

import logging
from collections.abc import AsyncIterator
from typing import Self

import aiohttp
import pytest

from bot.config import config
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.services.llm import LLMClient
from bot.services.llm import client as client_module
from bot.services.llm.streaming import stream_unlimited


class AsyncLines:
    """Async lines."""

    def __init__(self, lines: object) -> None:
        """Initializes the test double."""
        self.lines = iter(lines)

    def __aiter__(self) -> "AsyncLines":
        """Returns the async iterator."""
        return self

    async def __anext__(self) -> str:
        """Returns the next item."""
        try:
            return next(self.lines)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeResponse:
    """Fake response."""

    def __init__(self, lines: object = (), status: int = 200, body: str = "") -> None:
        """Initializes the test double."""
        self.content = AsyncLines(lines)
        self.status = status
        self.body = body

    async def __aenter__(self) -> Self:
        """Enters the async context."""
        return self

    async def __aexit__(
        self, _exc_type: object, _exc: object, _traceback: object
    ) -> bool:
        """Leaves the async context."""
        return False

    async def text(self) -> str:
        """Text."""
        return self.body


class FakeSession:
    """Fake session."""

    def __init__(self, response: object) -> None:
        """Initializes the test double."""
        self.response = response
        self.calls = []

    def post(self, url: str, **kwargs: object) -> "FakeResponse":
        """Post."""
        self.calls.append((url, kwargs))
        return self.response


async def collect(stream: object) -> list[object]:
    """Collect."""
    return [chunk async for chunk in stream]


@pytest.mark.asyncio
async def test_stream_unlimited_yields_content_and_ignores_non_content_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stream unlimited yields content and ignores non content chunks."""
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

    async def get_session() -> "FakeSession":
        return session

    normalized = []

    def normalize(messages: object) -> list[object]:
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
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Stream unlimited raises api error with response details."""
    private_detail = "prompt fragment\nsecond line"
    session = FakeSession(FakeResponse(status=503, body=private_detail))
    client = LLMClient()

    async def get_session() -> "FakeSession":
        return session

    monkeypatch.setattr(client, "_get_session", get_session)

    with (
        caplog.at_level(logging.ERROR, logger="bot.services.llm.streaming"),
        pytest.raises(LLMAPIError) as error,
    ):
        await collect(stream_unlimited(client, []))

    assert error.value.status == 503
    assert error.value.detail == private_detail
    assert r"prompt fragment\nsecond line" in caplog.text
    assert "prompt fragment\nsecond line" not in caplog.text


@pytest.mark.asyncio
async def test_stream_unlimited_converts_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stream unlimited converts timeout."""
    client = LLMClient()

    async def get_session() -> None:
        raise TimeoutError

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMTimeoutError, match="timed out"):
        await collect(stream_unlimited(client, []))


@pytest.mark.asyncio
async def test_stream_unlimited_converts_aiohttp_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stream unlimited converts aiohttp client error."""
    client = LLMClient()

    async def get_session() -> None:
        msg = "connection refused"
        raise aiohttp.ClientConnectionError(msg)

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMUnavailableError, match="Could not connect"):
        await collect(stream_unlimited(client, []))


@pytest.mark.asyncio
async def test_llm_client_unlimited_stream_delegates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Llm client unlimited stream delegates."""
    client = LLMClient()
    messages = [{"role": "user", "content": "hello"}]
    calls = []

    async def fake_stream(
        client_arg: object, messages_arg: object
    ) -> AsyncIterator[str]:
        calls.append((client_arg, messages_arg))
        yield "hello"
        yield " world"

    monkeypatch.setattr(client_module, "stream_unlimited", fake_stream)

    assert await collect(client._stream_unlimited(messages)) == ["hello", " world"]
    assert calls == [(client, messages)]


@pytest.mark.asyncio
async def test_public_stream_keeps_semaphore_wrapping_unlimited_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public stream keeps semaphore wrapping unlimited stream."""
    client = LLMClient()
    messages = [{"role": "user", "content": "hello"}]
    calls = []

    async def fake_stream(
        self: object, received_messages: object
    ) -> AsyncIterator[str]:
        calls.append((self, received_messages))
        yield "token"

    monkeypatch.setattr(client, "_stream_unlimited", fake_stream.__get__(client))

    assert await collect(client.stream(messages)) == ["token"]
    assert calls == [(client, messages)]
