# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake OpenAI-compatible LLM support server."""

import aiohttp
import pytest

from bot.config import config
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.services.llm import LLMClient
from tests.support.fake_llm import FakeLLM, FakeLLMOptions


def _configure_client(
    monkeypatch: pytest.MonkeyPatch,
    server: FakeLLM,
    *,
    context_size: int | None = None,
    timeout: float = 5.0,
) -> None:
    """Point the real LLM client at the fake server."""
    monkeypatch.setattr(config, "LLM_BASE_URL", f"{server.base_url}v1")
    monkeypatch.setattr(config, "LLM_API_KEY", server.api_key or "")
    monkeypatch.setattr(config, "LLM_MODEL", server.model)
    monkeypatch.setattr(config, "LLM_CONTEXT_SIZE", context_size)
    monkeypatch.setattr(config, "LLM_TOKEN_COUNTING", "auto")
    monkeypatch.setattr(config, "LLM_TIMEOUT", timeout)


@pytest.mark.asyncio
async def test_fake_llm_supports_real_client_and_non_streaming_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise context discovery, tokenization and generation over HTTP."""
    messages = [{"role": "user", "content": "hello world"}]
    async with FakeLLM() as server:
        _configure_client(monkeypatch, server)
        client = LLMClient()
        try:
            assert await client.get_context_size() == 8192
            assert await client.get_token_counting_mode() == "llamacpp"
            assert await client.count_tokens(messages) == 2
            assert await client.count_text_tokens("hello world") == 2
            assert [token async for token in client.stream(messages)] == [
                "Hello",
                ", world!",
            ]
            assert await client.health_check() == (True, "Доступен")

            async with (
                aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {server.api_key}"}
                ) as session,
                session.post(
                    f"{server.base_url}v1/chat/completions",
                    json={
                        "model": server.model,
                        "messages": messages,
                        "stream": False,
                    },
                ) as response,
            ):
                assert response.status == 200
                payload = await response.json()

            assert payload["choices"][0]["message"]["content"] == "Hello, world!"
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_fake_llm_can_omit_context_metadata_and_tokenizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose a standard model card without optional llama.cpp capabilities."""
    options = FakeLLMOptions(
        include_context_metadata=False,
        tokenizer_available=False,
    )
    async with FakeLLM(options=options) as server:
        _configure_client(monkeypatch, server, context_size=4096)
        async with (
            aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {server.api_key}"}
            ) as session,
            session.get(f"{server.base_url}v1/models") as response,
        ):
            payload = await response.json()
        assert "max_model_len" not in payload["data"][0]

        client = LLMClient()
        try:
            assert await client.get_context_size() == 4096
            assert await client.get_token_counting_mode() == "estimate"
            assert await client.count_text_tokens("abcdef") == 2
        finally:
            await client.close()


@pytest.mark.parametrize("status", [401, 429, 500])
@pytest.mark.asyncio
async def test_fake_llm_can_return_configured_http_errors(
    status: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return configured OpenAI-compatible generation errors."""
    async with FakeLLM(options=FakeLLMOptions(chat_status=status)) as server:
        _configure_client(monkeypatch, server)
        client = LLMClient()
        try:
            with pytest.raises(LLMAPIError) as error:
                async for _token in client.stream(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass
            assert error.value.status == status
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_fake_llm_can_delay_the_first_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real client's request timeout before the first token."""
    options = FakeLLMOptions(first_token_delay=0.05)
    async with FakeLLM(options=options) as server:
        _configure_client(monkeypatch, server, timeout=0.01)
        client = LLMClient()
        try:
            with pytest.raises(LLMTimeoutError):
                async for _token in client.stream(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_fake_llm_can_drop_connection_mid_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Close the connection after sending the first SSE chunk."""
    options = FakeLLMOptions(drop_after_chunks=1)
    async with FakeLLM(options=options) as server:
        _configure_client(monkeypatch, server)
        client = LLMClient()
        try:
            stream = client.stream([{"role": "user", "content": "hello"}])
            assert await anext(stream) == "Hello"
            with pytest.raises(LLMUnavailableError):
                await anext(stream)
        finally:
            await client.close()
