# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm streaming."""

import logging
from collections.abc import AsyncIterator
from typing import Self

import aiohttp
import pytest

from bot_obormot.errors import (
    LLMAPIError,
    LLMEmptyResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from bot_obormot.services.llm import LLMClient
from bot_obormot.services.llm import client as client_module
from bot_obormot.services.llm.streaming import stream_unlimited
from tests.support.settings import make_settings


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
    settings = make_settings()
    client = LLMClient(settings)

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
            f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions",
            {
                "json": {
                    "model": settings.LLM_MODEL,
                    "messages": [{"role": "user", "content": "normalized"}],
                    "temperature": settings.LLM_TEMPERATURE,
                    "top_p": settings.LLM_TOP_P,
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "stream": True,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_stream_unlimited_raises_api_error_with_response_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    private_detail = "prompt fragment\nsecond line"
    session = FakeSession(FakeResponse(status=503, body=private_detail))
    client = LLMClient(make_settings())

    async def get_session() -> "FakeSession":
        return session

    monkeypatch.setattr(client, "_get_session", get_session)

    with (
        caplog.at_level(logging.ERROR, logger="bot_obormot.services.llm.streaming"),
        pytest.raises(LLMAPIError) as error,
    ):
        await collect(stream_unlimited(client, []))

    expected_status = 503
    assert error.value.status == expected_status
    assert error.value.detail == private_detail
    escaped_prompt = r"prompt fragment\nsecond line"
    assert escaped_prompt in caplog.text
    raw_prompt = "prompt fragment\nsecond line"
    assert raw_prompt not in caplog.text


@pytest.mark.asyncio
async def test_stream_unlimited_converts_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient(make_settings())

    async def get_session() -> None:
        raise TimeoutError

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMTimeoutError, match="timed out"):
        await collect(stream_unlimited(client, []))


@pytest.mark.asyncio
async def test_stream_unlimited_converts_aiohttp_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient(make_settings())

    async def get_session() -> None:
        msg = "connection refused"
        raise aiohttp.ClientConnectionError(msg)

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMUnavailableError, match="Could not connect"):
        await collect(stream_unlimited(client, []))


async def _stream_through_patched_module(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[str], list[tuple[object, object]], LLMClient, list[dict[str, str]]]:
    client = LLMClient(make_settings())
    messages = [{"role": "user", "content": "Привет, мир"}]
    calls: list[tuple[object, object]] = []

    async def fake_stream(
        client_arg: object, messages_arg: object
    ) -> AsyncIterator[str]:
        calls.append((client_arg, messages_arg))
        yield "hello"
        yield " world"

    monkeypatch.setattr(client_module, "stream_unlimited", fake_stream)
    tokens = await collect(client.stream(messages))
    return tokens, calls, client, messages


@pytest.mark.asyncio
async def test_public_stream_yields_the_unlimited_stream_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens, _calls, _client, _messages = await _stream_through_patched_module(
        monkeypatch
    )
    expected = ["hello", " world"]
    assert tokens == expected, "the public stream must yield every token"


@pytest.mark.asyncio
async def test_public_stream_passes_the_client_and_messages_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _tokens, calls, client, messages = await _stream_through_patched_module(monkeypatch)
    expected = [(client, messages)]
    assert calls == expected, "the unlimited stream must receive the request once"


def _client_with_lines(
    monkeypatch: pytest.MonkeyPatch, lines: list[bytes]
) -> LLMClient:
    client = LLMClient(make_settings())
    session = FakeSession(FakeResponse(lines))

    async def get_session() -> "FakeSession":
        return session

    monkeypatch.setattr(client, "_get_session", get_session)
    return client


@pytest.mark.asyncio
async def test_stream_unlimited_reports_reasoning_that_used_the_whole_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = _client_with_lines(
        monkeypatch,
        [
            'data: {"choices":[{"delta":{"reasoning_content":"думаю"}}]}\n'.encode(),
            b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n',
            b"data: [DONE]\n",
        ],
    )

    with (
        caplog.at_level(logging.WARNING, logger="bot_obormot.services.llm.streaming"),
        pytest.raises(LLMEmptyResponseError) as error,
    ):
        await collect(stream_unlimited(client, []))

    expected_finish_reason = "length"
    assert error.value.finish_reason == expected_finish_reason
    stream_state = "answer_produced=False, reasoning_seen=True"
    assert stream_state in caplog.text
    max_tokens_setting = "LLM_MAX_TOKENS"
    assert max_tokens_setting in caplog.text


@pytest.mark.asyncio
async def test_stream_unlimited_warns_but_keeps_an_answer_cut_by_the_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    client = _client_with_lines(
        monkeypatch,
        [
            b'data: {"choices":[{"delta":{"content":"| a |"}}]}\n',
            b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n',
        ],
    )

    with caplog.at_level(logging.WARNING, logger="bot_obormot.services.llm.streaming"):
        result = await collect(stream_unlimited(client, []))

    assert result == ["| a |"]
    stream_state = "answer_produced=True"
    assert stream_state in caplog.text


@pytest.mark.asyncio
async def test_stream_unlimited_leaves_a_normal_empty_stop_to_the_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_with_lines(
        monkeypatch,
        [b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'],
    )

    assert await collect(stream_unlimited(client, [])) == []
