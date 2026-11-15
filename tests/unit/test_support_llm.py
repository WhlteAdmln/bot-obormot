# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake OpenAI-compatible LLM support server."""

import asyncio
from contextlib import suppress
from dataclasses import replace

import aiohttp
import pytest

from bot.config import config
from bot.config.settings import Settings
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.services.llm import LLMClient
from tests.support.fake_llm import FakeLLM, FakeLLMOptions


def _with_token_counting(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    mode: str,
) -> Settings:
    """Return settings with the requested token counting mode."""
    updates = {"LLM_TOKEN_COUNTING": mode}
    monkeypatch.setattr(config, "LLM_TOKEN_COUNTING", mode)
    return replace(settings, **updates)


def _configure_client(
    monkeypatch: pytest.MonkeyPatch,
    server: FakeLLM,
    *,
    context_size: int | None = None,
    timeout: float = 5.0,
) -> Settings:
    """Build settings for the fake LLM server."""
    settings = replace(
        Settings(),
        LLM_BASE_URL=f"{server.base_url}v1",
        LLM_API_KEY=server.api_key or "",
        LLM_MODEL=server.model,
        LLM_CONTEXT_SIZE=context_size,
        LLM_TIMEOUT=timeout,
    )

    # Keep legacy consumers configured until their migration is complete.
    for name in (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_CONTEXT_SIZE",
        "LLM_TIMEOUT",
        "LLM_TEMPERATURE",
        "LLM_TOP_P",
        "LLM_MAX_TOKENS",
    ):
        monkeypatch.setattr(config, name, getattr(settings, name))

    return _with_token_counting(monkeypatch, settings, "auto")


@pytest.mark.asyncio
async def test_fake_llm_supports_real_client_and_non_streaming_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise context discovery, tokenization and generation over HTTP."""
    messages = [{"role": "user", "content": "hello world"}]
    async with FakeLLM() as server:
        client = LLMClient(settings=_configure_client(monkeypatch, server))
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
        client = LLMClient(
            settings=_configure_client(
                monkeypatch,
                server,
                context_size=4096,
            )
        )
        try:
            async with (
                aiohttp.ClientSession(
                    headers={"Authorization": f"Bearer {server.api_key}"}
                ) as session,
                session.get(f"{server.base_url}v1/models") as response,
            ):
                payload = await response.json()
            assert "max_model_len" not in payload["data"][0]

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
        client = LLMClient(settings=_configure_client(monkeypatch, server))
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
        client = LLMClient(
            settings=_configure_client(
                monkeypatch,
                server,
                timeout=0.01,
            )
        )
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
        client = LLMClient(settings=_configure_client(monkeypatch, server))
        try:
            stream = client.stream([{"role": "user", "content": "hello"}])
            assert await anext(stream) == "Hello"
            with pytest.raises(LLMUnavailableError):
                await anext(stream)
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_real_client_session_reuses_and_recreates_closed_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reuse a real HTTP session and recreate it after closure."""
    async with FakeLLM(api_key=None) as server:
        client = LLMClient(settings=_configure_client(monkeypatch, server))
        try:
            await client.start()
            first = await client.get_session()
            assert await client.get_session() is first
            assert first.timeout.total == 5.0

            await first.close()
            second = await client.get_session()

            assert second is not first
            assert not second.closed
            assert await client.health_check() == (True, "Доступен")

            await client.close()
            assert second.closed
            assert client.session is None
        finally:
            await client.close()


@pytest.mark.parametrize(
    ("api_key", "expected_header"),
    [
        ("secret-api-key", "Bearer secret-api-key"),
        ("", None),
        ("   ", None),
        ("not-needed", None),
    ],
)
@pytest.mark.asyncio
async def test_real_client_session_configures_auth_header(
    api_key: str,
    expected_header: str | None,
) -> None:
    """Configure the real session authorization header."""
    settings = replace(Settings(), LLM_API_KEY=api_key)
    client = LLMClient(settings=settings)
    try:
        session = await client.get_session()
        assert session.headers.get("Authorization") == expected_header
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stream_can_be_cancelled_by_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel a pending stream without invalidating the shared session."""
    options = FakeLLMOptions(first_token_delay=0.1)
    async with FakeLLM(options=options) as server:
        client = LLMClient(settings=_configure_client(monkeypatch, server))
        stream = client.stream([{"role": "user", "content": "hello"}])
        pending_token = asyncio.create_task(anext(stream))

        try:
            await asyncio.wait_for(server.stream_started.wait(), timeout=1)
            pending_token.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending_token

            assert await client.health_check() == (True, "Доступен")
        finally:
            if not pending_token.done():
                pending_token.cancel()
                with suppress(asyncio.CancelledError):
                    await pending_token
            await stream.aclose()
            await client.close()


@pytest.mark.asyncio
async def test_real_client_fits_very_long_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prune old exchanges while preserving the newest history."""
    async with FakeLLM() as server:
        settings = replace(
            _configure_client(monkeypatch, server),
            LLM_MAX_TOKENS=128,
        )
        monkeypatch.setattr(config, "LLM_MAX_TOKENS", 128)
        client = LLMClient(settings=settings)
        history: list[dict[str, str]] = []
        for index in range(4):
            history.extend(
                [
                    {
                        "role": "user",
                        "content": f"question-{index} " + "detail " * 1600,
                    },
                    {
                        "role": "assistant",
                        "content": f"answer-{index} " + "detail " * 1600,
                    },
                ]
            )

        try:
            result = await client.fit_messages_to_context(
                "system prompt",
                history,
                "current question",
            )
            assert result[1:5] == history[4:]
            assert result[-1] == {
                "role": "user",
                "content": "current question",
            }
            assert len(result) < len(history) + 2
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_real_client_estimates_message_tokens_when_tokenizer_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Estimate message tokens when the server has no tokenizer."""
    options = FakeLLMOptions(tokenizer_available=False)
    async with FakeLLM(options=options) as server:
        client = LLMClient(settings=_configure_client(monkeypatch, server))
        try:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "one two three"},
                        {"type": "image_url"},
                    ],
                }
            ]

            assert await client.get_token_counting_mode() == "estimate"
            assert await client.count_tokens(messages) == 13
        finally:
            await client.close()


@pytest.mark.parametrize(
    ("options", "operation"),
    [
        (FakeLLMOptions(apply_template_status=500), "messages"),
        (FakeLLMOptions(tokenize_status=500), "messages"),
        (FakeLLMOptions(tokenize_status=500), "text"),
    ],
)
@pytest.mark.asyncio
async def test_real_client_maps_tokenizer_http_errors(
    options: FakeLLMOptions,
    operation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map tokenizer endpoint HTTP failures to the public API error."""
    async with FakeLLM(options=options) as server:
        settings = _with_token_counting(
            monkeypatch,
            _configure_client(monkeypatch, server),
            "llamacpp",
        )
        client = LLMClient(settings=settings)
        try:
            request = (
                client.count_tokens([{"role": "user", "content": "hello world"}])
                if operation == "messages"
                else client.count_text_tokens("hello world")
            )
            with pytest.raises(LLMAPIError) as error:
                await request

            assert error.value.status == 500
        finally:
            await client.close()


@pytest.mark.parametrize("operation", ["messages", "text"])
@pytest.mark.asyncio
async def test_real_client_maps_tokenizer_timeout(
    operation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map tokenizer endpoint timeouts to the public timeout error."""
    options = FakeLLMOptions(tokenize_delay=0.05)
    async with FakeLLM(options=options) as server:
        settings = _with_token_counting(
            monkeypatch,
            _configure_client(
                monkeypatch,
                server,
                timeout=0.01,
            ),
            "llamacpp",
        )
        client = LLMClient(settings=settings)
        try:
            request = (
                client.count_tokens([{"role": "user", "content": "hello world"}])
                if operation == "messages"
                else client.count_text_tokens("hello world")
            )
            with pytest.raises(LLMTimeoutError):
                await request
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_context_size_uses_single_model_fallback_and_caches_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the only model entry when its ID does not match the setting."""
    async with FakeLLM() as server:
        settings = replace(
            _configure_client(monkeypatch, server, context_size=None),
            LLM_MODEL="configured-model",
        )
        monkeypatch.setattr(config, "LLM_MODEL", "configured-model")
        client = LLMClient(settings=settings)
        try:
            assert await client.get_context_size() == 8192
            assert await client.get_context_size() == 8192
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_context_size_fails_when_server_has_no_context_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Require a setting when neither server endpoint reports context size."""
    options = FakeLLMOptions(include_context_metadata=False)
    async with FakeLLM(options=options) as server:
        client = LLMClient(
            settings=_configure_client(
                monkeypatch,
                server,
                context_size=None,
            )
        )
        try:
            with pytest.raises(LLMUnavailableError, match="LLM_CONTEXT_SIZE"):
                await client.get_context_size()
        finally:
            await client.close()


@pytest.mark.asyncio
async def test_real_client_handles_unavailable_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handle connection failures in context, tokenizer and health requests."""
    server = FakeLLM(api_key=None)
    await server.__aenter__()
    settings = _configure_client(monkeypatch, server, context_size=None)
    await server.__aexit__(None, None, None)

    client = LLMClient(settings=settings)
    try:
        with pytest.raises(LLMUnavailableError, match="LLM_CONTEXT_SIZE"):
            await client.get_context_size()

        assert await client.get_token_counting_mode() == "estimate"
    finally:
        await client.close()

    client = LLMClient(settings=_with_token_counting(monkeypatch, settings, "llamacpp"))
    try:
        with pytest.raises(LLMUnavailableError):
            await client.count_tokens([{"role": "user", "content": "hello"}])
        with pytest.raises(LLMUnavailableError):
            await client.count_text_tokens("hello")

        assert await client.health_check() == (False, "LLM-сервер недоступен")
    finally:
        await client.close()
