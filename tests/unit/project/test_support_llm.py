# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake OpenAI-compatible LLM support server."""

import asyncio
from contextlib import aclosing
from dataclasses import replace

import aiohttp
import pytest

from bot_obormot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot_obormot.settings import Settings
from tests.support.fake_llm import (
    FakeChatOptions,
    FakeLLM,
    FakeLLMOptions,
    FakeTokenizerOptions,
    open_llm_client,
)


def _with_token_counting(settings: Settings, mode: str) -> Settings:
    """Return settings with the requested token counting mode."""
    return replace(settings, LLM_TOKEN_COUNTING=mode)


def _configure_client(
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
    return _with_token_counting(settings, "auto")


@pytest.mark.asyncio
async def test_fake_llm_supports_real_client_and_non_streaming_requests() -> None:
    messages = [{"role": "user", "content": "hello world"}]
    async with (
        FakeLLM() as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        expected_number = 8192
        assert await client.get_context_size() == expected_number
        expected_text = "llamacpp"
        assert await client.get_token_counting_mode() == expected_text
        expected_number = 2
        assert await client.count_tokens(messages) == expected_number
        expected_number = 2
        assert await client.count_text_tokens("hello world") == expected_number
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
            expected_status = 200
            assert response.status == expected_status
            payload = await response.json()

        expected_content = "Hello, world!"
        assert payload["choices"][0]["message"]["content"] == expected_content


@pytest.mark.asyncio
async def test_fake_llm_can_omit_context_metadata_and_tokenizer() -> None:
    options = FakeLLMOptions(
        tokenizer=FakeTokenizerOptions(available=False),
        include_context_metadata=False,
    )
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(
            _configure_client(
                server,
                context_size=4096,
            )
        ) as client,
    ):
        async with (
            aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {server.api_key}"}
            ) as session,
            session.get(f"{server.base_url}v1/models") as response,
        ):
            payload = await response.json()
        length_field = "max_model_len"
        assert length_field not in payload["data"][0]

        expected_number = 4096
        assert await client.get_context_size() == expected_number
        expected_text = "estimate"
        assert await client.get_token_counting_mode() == expected_text
        expected_number = 2
        assert await client.count_text_tokens("abcdef") == expected_number


@pytest.mark.parametrize("status", [401, 429, 500])
@pytest.mark.asyncio
async def test_fake_llm_can_return_configured_http_errors(status: int) -> None:
    async with (
        FakeLLM(options=FakeLLMOptions(chat=FakeChatOptions(status=status))) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        with pytest.raises(LLMAPIError) as error:
            async for _token in client.stream([{"role": "user", "content": "hello"}]):
                pass
        assert error.value.status == status


@pytest.mark.asyncio
async def test_fake_llm_can_delay_the_first_token() -> None:
    options = FakeLLMOptions(chat=FakeChatOptions(first_token_delay=0.05))
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(
            _configure_client(
                server,
                timeout=0.01,
            )
        ) as client,
    ):
        with pytest.raises(LLMTimeoutError):
            async for _token in client.stream([{"role": "user", "content": "hello"}]):
                pass


@pytest.mark.asyncio
async def test_fake_llm_can_drop_connection_mid_stream() -> None:
    options = FakeLLMOptions(chat=FakeChatOptions(drop_after_chunks=1))
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        stream = client.stream([{"role": "user", "content": "hello"}])
        expected_text = "Hello"
        assert await anext(stream) == expected_text
        with pytest.raises(LLMUnavailableError):
            await anext(stream)


@pytest.mark.asyncio
async def test_real_client_session_reuses_and_recreates_closed_session() -> None:
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        await client.start()
        first = await client.get_session()
        assert await client.get_session() is first
        expected_total = 5.0
        assert first.timeout.total == expected_total

        await first.close()
        second = await client.get_session()

        assert second is not first
        assert not second.closed
        assert await client.health_check() == (True, "Доступен")

        await client.close()
        assert second.closed
        assert client.session is None


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
    settings = replace(Settings(), LLM_API_KEY=api_key)
    async with open_llm_client(settings) as client:
        session = await client.get_session()
        assert session.headers.get("Authorization") == expected_header


@pytest.mark.asyncio
async def test_stream_can_be_cancelled_by_client() -> None:
    options = FakeLLMOptions(chat=FakeChatOptions(first_token_delay=0.1))
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
        aclosing(client.stream([{"role": "user", "content": "hello"}])) as stream,
    ):
        pending_token = asyncio.create_task(anext(stream))
        await asyncio.wait_for(server.stream_started.wait(), timeout=1)
        pending_token.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_token
        assert await client.health_check() == (True, "Доступен")


@pytest.mark.asyncio
async def test_real_client_fits_very_long_history() -> None:
    async with FakeLLM() as server:
        settings = replace(
            _configure_client(server),
            LLM_MAX_TOKENS=128,
        )
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

        async with open_llm_client(settings) as client:
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


@pytest.mark.asyncio
async def test_real_client_estimates_message_tokens_when_tokenizer_is_missing() -> None:
    options = FakeLLMOptions(tokenizer=FakeTokenizerOptions(available=False))
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "one two three"},
                    {"type": "image_url"},
                ],
            }
        ]

        expected_text = "estimate"
        assert await client.get_token_counting_mode() == expected_text
        expected_number = 13
        assert await client.count_tokens(messages) == expected_number


@pytest.mark.parametrize(
    ("options", "operation"),
    [
        (
            FakeLLMOptions(tokenizer=FakeTokenizerOptions(apply_template_status=500)),
            "messages",
        ),
        (
            FakeLLMOptions(tokenizer=FakeTokenizerOptions(tokenize_status=500)),
            "messages",
        ),
        (FakeLLMOptions(tokenizer=FakeTokenizerOptions(tokenize_status=500)), "text"),
    ],
)
@pytest.mark.asyncio
async def test_real_client_maps_tokenizer_http_errors(
    options: FakeLLMOptions,
    operation: str,
) -> None:
    async with FakeLLM(options=options) as server:
        settings = _with_token_counting(
            _configure_client(server),
            "llamacpp",
        )
        async with open_llm_client(settings) as client:
            expected_operation = "messages"
            request = (
                client.count_tokens([{"role": "user", "content": "hello world"}])
                if operation == expected_operation
                else client.count_text_tokens("hello world")
            )
            with pytest.raises(LLMAPIError) as error:
                await request

            expected_status = 500
            assert error.value.status == expected_status


@pytest.mark.parametrize("operation", ["messages", "text"])
@pytest.mark.asyncio
async def test_real_client_maps_tokenizer_timeout(operation: str) -> None:
    options = FakeLLMOptions(tokenizer=FakeTokenizerOptions(tokenize_delay=0.05))
    async with FakeLLM(options=options) as server:
        settings = _with_token_counting(
            _configure_client(
                server,
                timeout=0.01,
            ),
            "llamacpp",
        )
        async with open_llm_client(settings) as client:
            expected_operation = "messages"
            request = (
                client.count_tokens([{"role": "user", "content": "hello world"}])
                if operation == expected_operation
                else client.count_text_tokens("hello world")
            )
            with pytest.raises(LLMTimeoutError):
                await request


@pytest.mark.asyncio
async def test_context_size_uses_single_model_fallback_and_caches_result() -> None:
    async with FakeLLM() as server:
        settings = replace(
            _configure_client(server, context_size=None),
            LLM_MODEL="configured-model",
        )
        async with open_llm_client(settings) as client:
            expected_number = 8192
            assert await client.get_context_size() == expected_number
            expected_number = 8192
            assert await client.get_context_size() == expected_number


@pytest.mark.asyncio
async def test_context_size_fails_when_server_has_no_context_metadata() -> None:
    options = FakeLLMOptions(include_context_metadata=False)
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(
            _configure_client(
                server,
                context_size=None,
            )
        ) as client,
    ):
        with pytest.raises(LLMUnavailableError, match="LLM_CONTEXT_SIZE"):
            await client.get_context_size()


@pytest.mark.asyncio
async def test_real_client_handles_unavailable_server() -> None:
    async with FakeLLM(api_key=None) as server:
        settings = _configure_client(server, context_size=None)

    async with open_llm_client(settings) as client:
        with pytest.raises(LLMUnavailableError, match="LLM_CONTEXT_SIZE"):
            await client.get_context_size()

        expected_text = "estimate"
        assert await client.get_token_counting_mode() == expected_text

    async with open_llm_client(_with_token_counting(settings, "llamacpp")) as client:
        with pytest.raises(LLMUnavailableError):
            await client.count_tokens([{"role": "user", "content": "hello"}])
        with pytest.raises(LLMUnavailableError):
            await client.count_text_tokens("hello")

        assert await client.health_check() == (False, "LLM-сервер недоступен")
