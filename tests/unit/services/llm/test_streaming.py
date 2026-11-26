# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm streaming."""

import logging
from collections.abc import AsyncIterator, Iterable
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
from bot_obormot.settings import Settings
from tests.support.settings import make_settings


class AsyncLines:
    """Async lines."""

    def __init__(self, lines: Iterable[bytes]) -> None:
        """Initializes the test double."""
        self.lines = iter(lines)

    def __aiter__(self) -> "AsyncLines":
        """Returns the async iterator."""
        return self

    async def __anext__(self) -> bytes:
        """Returns the next item."""
        try:
            return next(self.lines)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeResponse:
    """Fake response."""

    def __init__(
        self, lines: Iterable[bytes] = (), status: int = 200, body: str = ""
    ) -> None:
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

    def __init__(self, response: FakeResponse) -> None:
        """Initializes the test double."""
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def post(self, url: str, **kwargs: object) -> "FakeResponse":
        """Post."""
        self.calls.append((url, kwargs))
        return self.response


async def collect(stream: AsyncIterator[object]) -> list[object]:
    """Collect."""
    return [chunk async for chunk in stream]


async def _stream_content_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[object], list[object], FakeSession, Settings]:
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

    normalized: list[object] = []

    def normalize(messages: object) -> list[object]:
        normalized.append(messages)
        return [{"role": "user", "content": "normalized"}]

    monkeypatch.setattr(client, "_get_session", get_session)
    monkeypatch.setattr(client, "_normalize_messages", normalize)

    result = await collect(
        stream_unlimited(client, [{"role": "user", "content": "raw"}])
    )
    return result, normalized, session, settings


@pytest.mark.asyncio
async def test_stream_unlimited_yields_content_and_ignores_non_content_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, _normalized, _session, _settings = await _stream_content_lines(monkeypatch)
    expected_tokens = ["Привет", "!"]
    assert result == expected_tokens, "the stream yields the wrong content"


@pytest.mark.asyncio
async def test_stream_unlimited_normalizes_the_messages_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, normalized, _session, _settings = await _stream_content_lines(monkeypatch)
    expected_normalized = [[{"role": "user", "content": "raw"}]]
    assert normalized == expected_normalized, "the messages are not normalized once"


@pytest.mark.asyncio
async def test_stream_unlimited_posts_the_streaming_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _result, _normalized, session, settings = await _stream_content_lines(monkeypatch)
    expected_calls = [
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
    assert session.calls == expected_calls, "the streaming request differs"


async def _fail_with_status(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    status: int,
    detail: str,
) -> LLMAPIError:
    session = FakeSession(FakeResponse(status=status, body=detail))
    client = LLMClient(make_settings())

    async def get_session() -> "FakeSession":
        return session

    monkeypatch.setattr(client, "_get_session", get_session)

    with (
        caplog.at_level(logging.ERROR, logger="bot_obormot.services.llm.streaming"),
        pytest.raises(LLMAPIError) as error,
    ):
        await collect(stream_unlimited(client, []))
    return error.value


@pytest.mark.asyncio
async def test_stream_unlimited_raises_api_error_with_the_response_status(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    expected_status = 503
    detail = "service is warming up"
    error = await _fail_with_status(monkeypatch, caplog, expected_status, detail)
    assert error.status == expected_status, "the error has the wrong status"


@pytest.mark.asyncio
async def test_stream_unlimited_raises_api_error_with_the_response_body(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    status = 502
    private_detail = "prompt fragment\nsecond line"
    error = await _fail_with_status(monkeypatch, caplog, status, private_detail)
    assert error.detail == private_detail, "the error has the wrong detail"


@pytest.mark.asyncio
async def test_stream_unlimited_logs_the_response_body_escaped(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    status = 500
    private_detail = "upstream said\nretry later"
    await _fail_with_status(monkeypatch, caplog, status, private_detail)
    escaped_detail = r"upstream said\nretry later"
    assert escaped_detail in caplog.text, "the logged body is not escaped"


@pytest.mark.asyncio
async def test_stream_unlimited_does_not_log_the_raw_response_body(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    status = 503
    private_detail = "prompt fragment\nsecond line"
    await _fail_with_status(monkeypatch, caplog, status, private_detail)
    assert private_detail not in caplog.text, "the raw body reached the log"


@pytest.mark.asyncio
async def test_stream_unlimited_converts_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient(make_settings())
    expected_text = "timed out"

    async def get_session() -> None:
        raise TimeoutError

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMTimeoutError) as excinfo:
        await collect(stream_unlimited(client, []))

    assert expected_text in str(excinfo.value), "the timeout is not reported"


@pytest.mark.asyncio
async def test_stream_unlimited_converts_aiohttp_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient(make_settings())
    expected_text = "Could not connect"

    async def get_session() -> None:
        msg = "connection refused"
        raise aiohttp.ClientConnectionError(msg)

    monkeypatch.setattr(client, "_get_session", get_session)

    with pytest.raises(LLMUnavailableError) as excinfo:
        await collect(stream_unlimited(client, []))

    assert expected_text in str(excinfo.value), "the connection error is not reported"


async def _stream_through_patched_module(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[list[object], list[tuple[object, object]], LLMClient, list[dict[str, str]]]:
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


async def _stream_reasoning_only(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> LLMEmptyResponseError:
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
    return error.value


@pytest.mark.asyncio
async def test_stream_unlimited_reports_reasoning_that_used_the_whole_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    error = await _stream_reasoning_only(monkeypatch, caplog)
    expected_finish_reason = "length"
    assert error.finish_reason == expected_finish_reason, "the finish reason differs"


@pytest.mark.asyncio
async def test_stream_unlimited_logs_the_state_of_a_reasoning_only_stream(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _stream_reasoning_only(monkeypatch, caplog)
    stream_state = "answer_produced=False, reasoning_seen=True"
    assert stream_state in caplog.text, "the stream state is not logged"


@pytest.mark.asyncio
async def test_stream_unlimited_names_the_token_limit_setting_in_the_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _stream_reasoning_only(monkeypatch, caplog)
    max_tokens_setting = "LLM_MAX_TOKENS"
    assert max_tokens_setting in caplog.text, "the log does not name the setting"


async def _stream_answer_cut_by_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> list[object]:
    client = _client_with_lines(
        monkeypatch,
        [
            b'data: {"choices":[{"delta":{"content":"| a |"}}]}\n',
            b'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n',
        ],
    )

    with caplog.at_level(logging.WARNING, logger="bot_obormot.services.llm.streaming"):
        return await collect(stream_unlimited(client, []))


@pytest.mark.asyncio
async def test_stream_unlimited_keeps_an_answer_cut_by_the_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    result = await _stream_answer_cut_by_limit(monkeypatch, caplog)
    expected_tokens = ["| a |"]
    assert result == expected_tokens, "the cut answer is dropped"


@pytest.mark.asyncio
async def test_stream_unlimited_warns_about_an_answer_cut_by_the_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await _stream_answer_cut_by_limit(monkeypatch, caplog)
    stream_state = "answer_produced=True"
    assert stream_state in caplog.text, "the cut answer is not reported"


@pytest.mark.asyncio
async def test_stream_unlimited_leaves_a_normal_empty_stop_to_the_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client_with_lines(
        monkeypatch,
        [b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n'],
    )
    expected_empty: list[object] = []

    result = await collect(stream_unlimited(client, []))

    assert result == expected_empty, "a normal empty stop yields tokens"
