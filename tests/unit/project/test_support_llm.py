# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the fake OpenAI-compatible LLM support server."""

import asyncio
from contextlib import aclosing
from dataclasses import replace
from typing import Any

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


async def _post_chat_completion(
    server: FakeLLM,
    messages: list[dict[str, str]],
) -> tuple[int, dict[str, Any]]:
    """Send a non-streaming chat request straight to the fake server."""
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
        payload: dict[str, Any] = await response.json()
        return response.status, payload


async def _get_models(server: FakeLLM) -> dict[str, Any]:
    """Read the model list straight from the fake server."""
    async with (
        aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {server.api_key}"}
        ) as session,
        session.get(f"{server.base_url}v1/models") as response,
    ):
        payload: dict[str, Any] = await response.json()
        return payload


def _long_history(rounds: int) -> list[dict[str, str]]:
    """Build a history that does not fit into the default context."""
    history: list[dict[str, str]] = []
    for index in range(rounds):
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
    return history


async def _fit_long_history(
    history: list[dict[str, str]],
    question: str,
) -> list[dict[str, Any]]:
    """Fit a long history into the context of the fake server."""
    async with FakeLLM() as server:
        settings = replace(
            _configure_client(server),
            LLM_MAX_TOKENS=128,
        )
        async with open_llm_client(settings) as client:
            result: list[dict[str, Any]] = await client.fit_messages_to_context(
                "system prompt",
                history,
                question,
            )
    return result


async def _closed_server_settings() -> Settings:
    """Return settings that point to a fake server that has stopped."""
    async with FakeLLM(api_key=None) as server:
        return _configure_client(server, context_size=None)


@pytest.mark.asyncio
async def test_fake_llm_reports_its_context_size() -> None:
    expected_size = 8192
    async with (
        FakeLLM() as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        size = await client.get_context_size()
    assert size == expected_size, "the fake server reported a wrong context size"


@pytest.mark.asyncio
async def test_fake_llm_offers_llamacpp_token_counting() -> None:
    expected_mode = "llamacpp"
    async with (
        FakeLLM() as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        mode = await client.get_token_counting_mode()
    assert mode == expected_mode, "the fake tokenizer was not detected"


@pytest.mark.asyncio
async def test_fake_llm_counts_message_tokens() -> None:
    messages = [{"role": "user", "content": "hello world"}]
    expected_count = 2
    async with (
        FakeLLM() as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        count = await client.count_tokens(messages)
    assert count == expected_count, "the fake tokenizer counted messages wrongly"


@pytest.mark.asyncio
async def test_fake_llm_counts_text_tokens() -> None:
    text = "hello world"
    expected_count = 2
    async with (
        FakeLLM() as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        count = await client.count_text_tokens(text)
    assert count == expected_count, "the fake tokenizer counted text wrongly"


@pytest.mark.asyncio
async def test_fake_llm_streams_the_default_answer() -> None:
    messages = [{"role": "user", "content": "say hello"}]
    expected_tokens = ["Hello", ", world!"]
    async with (
        FakeLLM() as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        tokens = [token async for token in client.stream(messages)]
    assert tokens == expected_tokens, "the fake server streamed a wrong answer"


@pytest.mark.asyncio
async def test_fake_llm_passes_the_health_check() -> None:
    expected_health = (True, "Доступен")
    async with (
        FakeLLM() as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        health = await client.health_check()
    assert health == expected_health, "the fake server failed the health check"


@pytest.mark.asyncio
async def test_fake_llm_accepts_non_streaming_requests() -> None:
    messages = [{"role": "user", "content": "answer without streaming"}]
    expected_status = 200
    async with FakeLLM() as server:
        status, _payload = await _post_chat_completion(server, messages)
    assert status == expected_status, "a non-streaming request was rejected"


@pytest.mark.asyncio
async def test_fake_llm_answers_non_streaming_requests_in_one_message() -> None:
    messages = [{"role": "user", "content": "hello in one piece"}]
    expected_content = "Hello, world!"
    async with FakeLLM() as server:
        _status, payload = await _post_chat_completion(server, messages)
    content = payload["choices"][0]["message"]["content"]
    assert content == expected_content, "the non-streaming answer is wrong"


@pytest.mark.asyncio
async def test_fake_llm_can_omit_context_metadata() -> None:
    options = FakeLLMOptions(include_context_metadata=False)
    length_field = "max_model_len"
    async with FakeLLM(options=options) as server:
        payload = await _get_models(server)
    assert length_field not in payload["data"][0], "the context metadata is present"


@pytest.mark.asyncio
async def test_real_client_uses_configured_context_size_without_metadata() -> None:
    options = FakeLLMOptions(
        tokenizer=FakeTokenizerOptions(available=False),
        include_context_metadata=False,
    )
    configured_size = 4096
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(
            _configure_client(server, context_size=configured_size)
        ) as client,
    ):
        size = await client.get_context_size()
    assert size == configured_size, "the configured context size was not used"


@pytest.mark.asyncio
async def test_real_client_estimates_tokens_without_tokenizer() -> None:
    options = FakeLLMOptions(
        tokenizer=FakeTokenizerOptions(available=False),
        include_context_metadata=False,
    )
    expected_mode = "estimate"
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server, context_size=2048)) as client,
    ):
        mode = await client.get_token_counting_mode()
    assert mode == expected_mode, "a missing tokenizer did not switch to estimates"


@pytest.mark.asyncio
async def test_real_client_estimates_text_tokens_without_tokenizer() -> None:
    options = FakeLLMOptions(
        tokenizer=FakeTokenizerOptions(available=False),
        include_context_metadata=False,
    )
    text = "abcdef"
    expected_count = 2
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server, context_size=4096)) as client,
    ):
        count = await client.count_text_tokens(text)
    assert count == expected_count, "the text token estimate is wrong"


@pytest.mark.parametrize("status", [401, 429, 500])
@pytest.mark.asyncio
async def test_fake_llm_can_return_configured_http_errors(status: int) -> None:
    async with (
        FakeLLM(options=FakeLLMOptions(chat=FakeChatOptions(status=status))) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        with pytest.raises(LLMAPIError) as error:
            async for _token in client.stream([{"role": "user", "content": "Ошибка?"}]):
                pass
    assert error.value.status == status, "the configured HTTP status was not raised"


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
        with pytest.raises(LLMTimeoutError) as error:
            async for _token in client.stream([{"role": "user", "content": "wait"}]):
                pass
    assert error.type is LLMTimeoutError, "a slow first token did not time out"


@pytest.mark.asyncio
async def test_fake_llm_sends_the_first_chunk_before_dropping_the_connection() -> None:
    options = FakeLLMOptions(chat=FakeChatOptions(drop_after_chunks=1))
    expected_chunk = "Hello"
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        stream = client.stream([{"role": "user", "content": "Оборвись 🔌"}])
        token = await anext(stream)
    assert token == expected_chunk, "the chunk before the drop was not delivered"


@pytest.mark.asyncio
async def test_fake_llm_can_drop_connection_mid_stream() -> None:
    options = FakeLLMOptions(chat=FakeChatOptions(drop_after_chunks=1))
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        stream = client.stream([{"role": "user", "content": "drop me"}])
        await anext(stream)
        with pytest.raises(LLMUnavailableError) as error:
            await anext(stream)
    assert error.type is LLMUnavailableError, "a dropped connection was not reported"


@pytest.mark.asyncio
async def test_real_client_session_reuses_an_open_session() -> None:
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        await client.start()
        first = await client.get_session()
        again = await client.get_session()
    assert again is first, "an open session was not reused"


@pytest.mark.asyncio
async def test_real_client_session_uses_the_configured_timeout() -> None:
    timeout = 7.5
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server, timeout=timeout)) as client,
    ):
        await client.start()
        session = await client.get_session()
        total = session.timeout.total
    assert total == timeout, "the session timeout differs from the settings"


@pytest.mark.asyncio
async def test_real_client_session_replaces_a_closed_session() -> None:
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        await client.start()
        first = await client.get_session()
        await first.close()
        second = await client.get_session()
    assert second is not first, "a closed session was reused"


@pytest.mark.asyncio
async def test_real_client_session_opens_the_replacement_session() -> None:
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        await client.start()
        first = await client.get_session()
        await first.close()
        second = await client.get_session()
        closed = second.closed
    assert closed is False, "the replacement session is already closed"


@pytest.mark.asyncio
async def test_real_client_session_passes_health_check_after_replacement() -> None:
    expected_health = (True, "Доступен")
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        await client.start()
        first = await client.get_session()
        await first.close()
        await client.get_session()
        health = await client.health_check()
    assert health == expected_health, "the replacement session cannot reach the LLM"


@pytest.mark.asyncio
async def test_real_client_close_closes_the_session() -> None:
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        await client.start()
        session = await client.get_session()
        await client.close()
    assert session.closed is True, "closing the client left its session open"


@pytest.mark.asyncio
async def test_real_client_close_forgets_the_session() -> None:
    async with (
        FakeLLM(api_key=None) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        await client.start()
        await client.get_session()
        await client.close()
        session = client.session
    assert session is None, "the closed client still holds a session"


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
        header = session.headers.get("Authorization")
    assert header == expected_header, "the authorization header is wrong"


@pytest.mark.asyncio
async def test_stream_can_be_cancelled_by_client() -> None:
    options = FakeLLMOptions(chat=FakeChatOptions(first_token_delay=0.1))
    expected_health = (True, "Доступен")
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
        aclosing(client.stream([{"role": "user", "content": "отмена…"}])) as stream,
    ):
        pending_token = asyncio.create_task(anext(stream))
        await asyncio.wait_for(server.stream_started.wait(), timeout=1)
        pending_token.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_token
        health = await client.health_check()
    assert health == expected_health, "a cancelled stream broke the client"


@pytest.mark.asyncio
async def test_real_client_keeps_the_latest_history_when_it_is_too_long() -> None:
    history = _long_history(4)
    result = await _fit_long_history(history, "current question")
    assert result[1:5] == history[4:], "the latest history was not kept"


@pytest.mark.asyncio
async def test_real_client_keeps_the_current_question_last() -> None:
    question = "what did we discuss?"
    expected_last = {"role": "user", "content": question}
    result = await _fit_long_history(_long_history(4), question)
    assert result[-1] == expected_last, "the current question is not the last message"


@pytest.mark.asyncio
async def test_real_client_drops_old_messages_from_a_long_history() -> None:
    history = _long_history(5)
    result = await _fit_long_history(history, "next question")
    assert len(result) < len(history) + 2, "no message of a long history was dropped"


@pytest.mark.asyncio
async def test_real_client_switches_to_estimates_when_tokenizer_is_missing() -> None:
    options = FakeLLMOptions(tokenizer=FakeTokenizerOptions(available=False))
    expected_mode = "estimate"
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        mode = await client.get_token_counting_mode()
    assert mode == expected_mode, "a missing tokenizer did not switch to estimates"


@pytest.mark.asyncio
async def test_real_client_estimates_message_tokens_when_tokenizer_is_missing() -> None:
    options = FakeLLMOptions(tokenizer=FakeTokenizerOptions(available=False))
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "one two three"},
                {"type": "image_url"},
            ],
        }
    ]
    expected_count = 13
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(_configure_client(server)) as client,
    ):
        count = await client.count_tokens(messages)
    assert count == expected_count, "the message token estimate is wrong"


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
    assert error.value.status == expected_status, "the tokenizer error was not mapped"


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
            with pytest.raises(LLMTimeoutError) as error:
                await request
    assert error.type is LLMTimeoutError, "a slow tokenizer did not time out"


@pytest.mark.asyncio
async def test_context_size_uses_single_model_fallback() -> None:
    expected_size = 8192
    async with FakeLLM() as server:
        settings = replace(
            _configure_client(server, context_size=None),
            LLM_MODEL="configured-model",
        )
        async with open_llm_client(settings) as client:
            size = await client.get_context_size()
    assert size == expected_size, "the single served model was not used"


@pytest.mark.asyncio
async def test_context_size_returns_the_same_value_on_repeated_calls() -> None:
    expected_size = 8192
    async with FakeLLM() as server:
        settings = replace(
            _configure_client(server, context_size=None),
            LLM_MODEL="another-configured-model",
        )
        async with open_llm_client(settings) as client:
            await client.get_context_size()
            size = await client.get_context_size()
    assert size == expected_size, "the cached context size differs"


@pytest.mark.asyncio
async def test_context_size_fails_when_server_has_no_context_metadata() -> None:
    options = FakeLLMOptions(include_context_metadata=False)
    setting_name = "LLM_CONTEXT_SIZE"
    async with (
        FakeLLM(options=options) as server,
        open_llm_client(
            _configure_client(
                server,
                context_size=None,
            )
        ) as client,
    ):
        with pytest.raises(LLMUnavailableError) as error:
            await client.get_context_size()
    assert setting_name in str(error.value), "the error does not name the setting"


@pytest.mark.asyncio
async def test_real_client_asks_for_context_size_when_server_is_unavailable() -> None:
    settings = await _closed_server_settings()
    setting_name = "LLM_CONTEXT_SIZE"
    async with open_llm_client(settings) as client:
        with pytest.raises(LLMUnavailableError) as error:
            await client.get_context_size()
    assert setting_name in str(error.value), "the error does not name the setting"


@pytest.mark.asyncio
async def test_real_client_estimates_tokens_when_server_is_unavailable() -> None:
    settings = await _closed_server_settings()
    expected_mode = "estimate"
    async with open_llm_client(settings) as client:
        mode = await client.get_token_counting_mode()
    assert mode == expected_mode, "an unavailable server did not switch to estimates"


@pytest.mark.asyncio
async def test_real_client_reports_unavailable_server_when_counting_messages() -> None:
    settings = _with_token_counting(await _closed_server_settings(), "llamacpp")
    async with open_llm_client(settings) as client:
        with pytest.raises(LLMUnavailableError) as error:
            await client.count_tokens([{"role": "user", "content": "are you there"}])
    assert error.type is LLMUnavailableError, "an unavailable tokenizer was hidden"


@pytest.mark.asyncio
async def test_real_client_reports_unavailable_server_when_counting_text() -> None:
    settings = _with_token_counting(await _closed_server_settings(), "llamacpp")
    async with open_llm_client(settings) as client:
        with pytest.raises(LLMUnavailableError) as error:
            await client.count_text_tokens("anyone home")
    assert error.type is LLMUnavailableError, "an unavailable tokenizer was hidden"


@pytest.mark.asyncio
async def test_real_client_fails_health_check_when_server_is_unavailable() -> None:
    settings = _with_token_counting(await _closed_server_settings(), "llamacpp")
    expected_health = (False, "LLM-сервер недоступен")
    async with open_llm_client(settings) as client:
        health = await client.health_check()
    assert health == expected_health, "an unavailable server passed the health check"
