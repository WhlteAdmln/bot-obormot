# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm context size."""

import logging
from dataclasses import replace

import pytest

from bot_obormot.errors import LLMUnavailableError
from bot_obormot.settings import Settings
from tests.support.llm_context_tokenizer import (
    FakeResponse,
    FakeSession,
    make_client,
    with_token_counting,
)


@pytest.mark.asyncio
async def test_context_size_reads_nested_setting_and_caches_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context size reads nested setting and caches result."""
    fake_session = FakeSession(
        [FakeResponse({"default_generation_settings": {"n_ctx": 8192}})]
    )
    client = make_client(monkeypatch, fake_session)

    result = await client.get_context_size()
    cached_result = await client.get_context_size()

    expected_size = 8192
    assert result == cached_result == expected_size
    assert len(fake_session.get_calls) == 1
    expected_get_calls = "http://llm.test/props"
    assert fake_session.get_calls[0][0] == expected_get_calls
    assert fake_session.get_calls[0][1]["params"] == {
        "model": client.settings.LLM_MODEL
    }


@pytest.mark.asyncio
async def test_context_size_rejects_boolean_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Context size rejects boolean value."""
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
    """Context size falls back to models metadata."""
    settings = with_token_counting(
        replace(
            Settings(),
            LLM_CONTEXT_SIZE=None,
            LLM_BASE_URL="http://llm.test/v1",
        ),
        "llamacpp",
    )
    fake_session = FakeSession(
        [
            FakeResponse({}, status=404, body="Not Found"),
            FakeResponse(
                {"data": [{"id": settings.LLM_MODEL, "max_model_len": 32768}]}
            ),
        ]
    )
    client = make_client(monkeypatch, fake_session, settings=settings)

    expected_number = 32768
    assert await client.get_context_size() == expected_number
    assert [call[0] for call in fake_session.get_calls] == [
        "http://llm.test/props",
        "http://llm.test/v1/models",
    ]


@pytest.mark.asyncio
async def test_configured_context_size_skips_server_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured context size skips server requests."""
    settings = with_token_counting(
        replace(
            Settings(),
            LLM_CONTEXT_SIZE=16384,
        ),
        "llamacpp",
    )
    fake_session = FakeSession([])
    client = make_client(monkeypatch, fake_session, settings=settings)

    expected_number = 16384
    assert await client.get_context_size() == expected_number
    expected_empty = []
    assert fake_session.get_calls == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_context_size_logs_sanitized_error_detail(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Context size logs sanitized error detail."""
    private_detail = "user prompt\nsecond line"
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

    expected_fragment = r"user prompt\nsecond line"
    assert expected_fragment in caplog.text
    expected_fragment = "user prompt\nsecond line"
    assert expected_fragment not in caplog.text
