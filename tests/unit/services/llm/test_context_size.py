# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm context size."""

import logging
from dataclasses import replace

import pytest

from bot_obormot.errors import LLMUnavailableError
from bot_obormot.services.llm import LLMClient
from bot_obormot.settings import Settings
from tests.support.llm_context_tokenizer import (
    FakeResponse,
    FakeSession,
    make_client,
    with_token_counting,
)


async def _read_twice(
    monkeypatch: pytest.MonkeyPatch, size: int
) -> tuple[LLMClient, FakeSession, int, int]:
    fake_session = FakeSession(
        [FakeResponse({"default_generation_settings": {"n_ctx": size}})]
    )
    client = make_client(monkeypatch, fake_session)
    result = await client.get_context_size()
    cached_result = await client.get_context_size()
    return client, fake_session, result, cached_result


def _fallback_session(model: str, size: int) -> FakeSession:
    return FakeSession(
        [
            FakeResponse({}, status=404, body="Not Found"),
            FakeResponse({"data": [{"id": model, "max_model_len": size}]}),
        ]
    )


def _fallback_settings() -> Settings:
    return with_token_counting(
        replace(
            Settings(),
            LLM_CONTEXT_SIZE=None,
            LLM_BASE_URL="http://llm.test/v1",
        ),
        "llamacpp",
    )


def _configured_settings(size: int) -> Settings:
    return with_token_counting(replace(Settings(), LLM_CONTEXT_SIZE=size), "llamacpp")


async def _fail_with_private_detail(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    private_detail: str,
) -> None:
    fake_session = FakeSession(
        [
            FakeResponse({}, status=503, body=private_detail),
            FakeResponse({}, status=503, body=private_detail),
        ]
    )
    client = make_client(monkeypatch, fake_session)

    with (
        caplog.at_level(logging.DEBUG, logger="bot_obormot.services.llm.context_size"),
        pytest.raises(LLMUnavailableError, match="LLM_CONTEXT_SIZE"),
    ):
        await client.get_context_size()


@pytest.mark.asyncio
async def test_context_size_reads_nested_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_size = 8192
    _client, _session, result, _cached = await _read_twice(monkeypatch, expected_size)
    assert result == expected_size, "the nested n_ctx was not read"


@pytest.mark.asyncio
async def test_context_size_returns_the_cached_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_size = 12288
    _client, _session, _result, cached = await _read_twice(monkeypatch, expected_size)
    assert cached == expected_size, "the cached size is wrong"


@pytest.mark.asyncio
async def test_context_size_requests_the_server_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    size = 6144
    expected_count = 1
    _client, fake_session, _result, _cached = await _read_twice(monkeypatch, size)
    assert len(fake_session.get_calls) == expected_count, "the result was not cached"


@pytest.mark.asyncio
async def test_context_size_requests_the_props_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    size = 2048
    expected_url = "http://llm.test/props"
    _client, fake_session, _result, _cached = await _read_twice(monkeypatch, size)
    url = fake_session.get_calls[0][0]
    assert url == expected_url, "the props endpoint was not requested"


@pytest.mark.asyncio
async def test_context_size_sends_the_model_as_a_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    size = 30000
    client, fake_session, _result, _cached = await _read_twice(monkeypatch, size)
    expected_params = {"model": client.settings.LLM_MODEL}
    params = fake_session.get_calls[0][1]["params"]
    assert params == expected_params, "the model parameter is wrong"


@pytest.mark.asyncio
async def test_context_size_rejects_boolean_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([FakeResponse({"n_ctx": True})])
    client = make_client(monkeypatch, fake_session)

    fake_session.responses.append(
        FakeResponse({"data": [{"id": client.settings.LLM_MODEL}]})
    )
    with pytest.raises(LLMUnavailableError, match="LLM_CONTEXT_SIZE"):
        await client.get_context_size()
    expected = 16384
    fake_session.responses.append(FakeResponse({"n_ctx": expected}))
    assert await client.get_context_size() == expected, "a failure must not be cached"


@pytest.mark.asyncio
async def test_context_size_falls_back_to_models_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _fallback_settings()
    expected_size = 32768
    fake_session = _fallback_session(settings.LLM_MODEL, expected_size)
    client = make_client(monkeypatch, fake_session, settings=settings)

    size = await client.get_context_size()

    assert size == expected_size, "the models metadata was not used"


@pytest.mark.asyncio
async def test_context_size_fallback_requests_props_then_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _fallback_settings()
    fake_session = _fallback_session(settings.LLM_MODEL, 65536)
    client = make_client(monkeypatch, fake_session, settings=settings)
    expected_urls = ["http://llm.test/props", "http://llm.test/v1/models"]

    await client.get_context_size()

    urls = [call[0] for call in fake_session.get_calls]
    assert urls == expected_urls, "the fallback requested the wrong endpoints"


@pytest.mark.asyncio
async def test_configured_context_size_is_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected_size = 16384
    fake_session = FakeSession([])
    settings = _configured_settings(expected_size)
    client = make_client(monkeypatch, fake_session, settings=settings)

    size = await client.get_context_size()

    assert size == expected_size, "the configured size was not used"


@pytest.mark.asyncio
async def test_configured_context_size_skips_server_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([])
    settings = _configured_settings(4000)
    client = make_client(monkeypatch, fake_session, settings=settings)

    await client.get_context_size()

    expected_empty: list[tuple[str, dict[str, object]]] = []
    assert fake_session.get_calls == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_context_size_logs_escaped_error_detail(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    private_detail = "user prompt\nsecond line"
    escaped_detail = r"user prompt\nsecond line"
    await _fail_with_private_detail(monkeypatch, caplog, private_detail)
    assert escaped_detail in caplog.text, "the escaped detail was not logged"


@pytest.mark.asyncio
async def test_context_size_does_not_log_raw_error_detail(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    private_detail = "мой вопрос\nвторая строка"
    await _fail_with_private_detail(monkeypatch, caplog, private_detail)
    assert private_detail not in caplog.text, "the raw detail was logged"
