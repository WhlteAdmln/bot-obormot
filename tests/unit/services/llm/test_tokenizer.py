# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm tokenizer."""

import logging

import pytest

from bot_obormot.errors import LLMAPIError, LLMUnavailableError
from bot_obormot.services.llm import LLMClient
from bot_obormot.settings import Settings
from tests.support.llm_context_tokenizer import (
    FakeResponse,
    FakeSession,
    make_client,
    with_token_counting,
)


@pytest.mark.asyncio
async def test_count_tokens_applies_template_then_tokenizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession(
        [
            FakeResponse({"prompt": "rendered prompt"}),
            FakeResponse({"tokens": [1, 2, 3, 4]}),
        ]
    )
    client = make_client(monkeypatch, fake_session)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,PRIVATE"},
                },
                {"type": "text", "text": "Описание"},
            ],
        }
    ]

    result = await client.count_tokens(messages)

    expected_result = 4
    assert result == expected_result
    assert [call[0] for call in fake_session.post_calls] == [
        "http://llm.test/apply-template",
        "http://llm.test/tokenize",
    ]
    apply_payload = fake_session.post_calls[0][1]["json"]
    assert apply_payload["model"] == client.settings.LLM_MODEL
    assert apply_payload["add_generation_prompt"] is True
    image_part = apply_payload["messages"][0]["content"][0]
    expected_url = "data:image/jpeg;base64,"
    assert image_part["image_url"]["url"] == expected_url
    assert messages[0]["content"][0]["image_url"]["url"].endswith("PRIVATE")

    tokenize_payload = fake_session.post_calls[1][1]["json"]
    assert tokenize_payload == {
        "model": client.settings.LLM_MODEL,
        "content": "rendered prompt",
        "add_special": True,
        "parse_special": True,
    }


@pytest.mark.asyncio
async def test_count_tokens_rejects_invalid_normalized_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([])
    client = make_client(monkeypatch, fake_session)
    monkeypatch.setattr(
        client,
        "_normalize_messages",
        lambda _messages: [{"role": "user", "content": 123}],
    )

    with pytest.raises(LLMUnavailableError, match="Invalid message content"):
        await client.count_tokens([{"role": "user", "content": "hello"}])

    expected_empty = []
    assert fake_session.post_calls == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_count_text_tokens_sends_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([FakeResponse({"tokens": [1, 2, 3]})])
    client = make_client(monkeypatch, fake_session)

    result = await client.count_text_tokens("Привет")

    expected_result = 3
    assert result == expected_result
    assert fake_session.post_calls == [
        (
            "http://llm.test/tokenize",
            {
                "json": {
                    "model": client.settings.LLM_MODEL,
                    "content": "Привет",
                    "add_special": False,
                    "parse_special": True,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_count_text_tokens_empty_text_skips_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient(settings=with_token_counting(Settings(), "llamacpp"))

    async def unexpected_session() -> None:
        msg = "HTTP session must not be requested for empty text"
        raise AssertionError(msg)

    monkeypatch.setattr(client, "_get_session", unexpected_session)

    assert await client.count_text_tokens("") == 0


@pytest.mark.asyncio
async def test_count_text_tokens_rejects_invalid_token_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([FakeResponse({"tokens": "not-a-list"})])
    client = make_client(monkeypatch, fake_session)

    with pytest.raises(LLMUnavailableError, match="invalid token list"):
        await client.count_text_tokens("hello")


@pytest.mark.asyncio
async def test_count_text_tokens_logs_sanitized_error_detail(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    private_detail = "user prompt\nsecond line"
    fake_session = FakeSession([FakeResponse({}, status=503, body=private_detail)])
    client = make_client(monkeypatch, fake_session)

    with (
        caplog.at_level(logging.ERROR, logger="bot_obormot.services.llm.tokenizer"),
        pytest.raises(LLMAPIError) as error,
    ):
        await client.count_text_tokens("private request")

    assert error.value.detail == private_detail
    escaped_prompt = r"user prompt\nsecond line"
    assert escaped_prompt in caplog.text
    raw_prompt = "user prompt\nsecond line"
    assert raw_prompt not in caplog.text
