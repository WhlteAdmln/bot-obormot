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


def _image_message(image_data: str, caption: str) -> list[dict[str, object]]:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_data}"},
                },
                {"type": "text", "text": caption},
            ],
        }
    ]


def _template_session(prompt: str, tokens: list[int]) -> FakeSession:
    return FakeSession(
        [
            FakeResponse({"prompt": prompt}),
            FakeResponse({"tokens": tokens}),
        ]
    )


@pytest.mark.asyncio
async def test_count_tokens_returns_the_token_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tokens = [17, 4, 950, 3]
    fake_session = _template_session("rendered prompt", tokens)
    client = make_client(monkeypatch, fake_session)
    messages = _image_message("PRIVATE", "Описание")

    result = await client.count_tokens(messages)

    expected_result = 4
    assert result == expected_result, "the token count differs from the token list"


@pytest.mark.asyncio
async def test_count_tokens_applies_template_then_tokenizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _template_session("<s>user: снимок</s>", [8, 1])
    client = make_client(monkeypatch, fake_session)
    messages = _image_message("c2VjcmV0", "снимок")

    await client.count_tokens(messages)

    expected_urls = [
        "http://llm.test/apply-template",
        "http://llm.test/tokenize",
    ]
    urls = [call[0] for call in fake_session.post_calls]
    assert urls == expected_urls, "the template and tokenize calls are out of order"


@pytest.mark.asyncio
async def test_count_tokens_sends_the_model_to_apply_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _template_session("rendered: фото", [2, 71, 6])
    client = make_client(monkeypatch, fake_session)
    messages = _image_message("QUJD", "фото кота")

    await client.count_tokens(messages)

    apply_payload = fake_session.post_calls[0][1]["json"]
    expected_model = client.settings.LLM_MODEL
    assert apply_payload["model"] == expected_model, "apply-template got another model"


@pytest.mark.asyncio
async def test_count_tokens_requests_the_generation_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _template_session("prompt with tail", [5])
    client = make_client(monkeypatch, fake_session)
    messages = _image_message("WFla", "Что здесь?")

    await client.count_tokens(messages)

    apply_payload = fake_session.post_calls[0][1]["json"]
    generation_prompt = apply_payload["add_generation_prompt"]
    assert generation_prompt is True, "the generation prompt was not requested"


@pytest.mark.asyncio
async def test_count_tokens_strips_image_data_from_the_template_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _template_session("stripped prompt", [9, 9, 9])
    client = make_client(monkeypatch, fake_session)
    messages = _image_message("PRIVATE", "Описание")

    await client.count_tokens(messages)

    apply_payload = fake_session.post_calls[0][1]["json"]
    image_part = apply_payload["messages"][0]["content"][0]
    expected_url = "data:image/jpeg;base64,"
    sent_url = image_part["image_url"]["url"]
    assert sent_url == expected_url, "the image data was sent to apply-template"


@pytest.mark.asyncio
async def test_count_tokens_keeps_the_caller_messages_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = _template_session("unchanged prompt", [12, 40])
    client = make_client(monkeypatch, fake_session)
    image_data = "UFJJVkFURTI="
    image_url = {"url": f"data:image/png;base64,{image_data}"}
    messages: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": image_url},
                {"type": "text", "text": "Подпись"},
            ],
        }
    ]

    await client.count_tokens(messages)

    original_url = image_url["url"]
    assert original_url.endswith(image_data), "the caller messages were modified"


@pytest.mark.asyncio
async def test_count_tokens_tokenizes_the_rendered_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered_prompt = "rendered prompt №2"
    fake_session = _template_session(rendered_prompt, [1, 2])
    client = make_client(monkeypatch, fake_session)
    messages = _image_message("Zm9v", "Описание снимка")

    await client.count_tokens(messages)

    expected_payload = {
        "model": client.settings.LLM_MODEL,
        "content": rendered_prompt,
        "add_special": True,
        "parse_special": True,
    }
    tokenize_payload = fake_session.post_calls[1][1]["json"]
    assert tokenize_payload == expected_payload, "the tokenize payload differs"


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
        await client.count_tokens([{"role": "user", "content": "Сколько токенов?"}])

    expected_empty: list[object] = []
    assert fake_session.post_calls == expected_empty, "invalid content reached HTTP"


@pytest.mark.asyncio
async def test_count_text_tokens_returns_the_token_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([FakeResponse({"tokens": [1, 2, 3]})])
    client = make_client(monkeypatch, fake_session)

    result = await client.count_text_tokens("Привет")

    expected_result = 3
    assert result == expected_result, "the token count differs from the token list"


@pytest.mark.asyncio
async def test_count_text_tokens_sends_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([FakeResponse({"tokens": [44, 8]})])
    client = make_client(monkeypatch, fake_session)
    text = "Здравствуй, мир"

    await client.count_text_tokens(text)

    expected_calls = [
        (
            "http://llm.test/tokenize",
            {
                "json": {
                    "model": client.settings.LLM_MODEL,
                    "content": text,
                    "add_special": False,
                    "parse_special": True,
                }
            },
        )
    ]
    assert fake_session.post_calls == expected_calls, "the tokenize request differs"


@pytest.mark.asyncio
async def test_count_text_tokens_empty_text_skips_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient(settings=with_token_counting(Settings(), "llamacpp"))

    async def unexpected_session() -> None:
        msg = "HTTP session must not be requested for empty text"
        raise AssertionError(msg)

    monkeypatch.setattr(client, "_get_session", unexpected_session)

    expected_count = 0
    result = await client.count_text_tokens("")
    assert result == expected_count, "empty text has tokens"


@pytest.mark.asyncio
async def test_count_text_tokens_rejects_invalid_token_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_session = FakeSession([FakeResponse({"tokens": "not-a-list"})])
    client = make_client(monkeypatch, fake_session)

    with pytest.raises(LLMUnavailableError) as error:
        await client.count_text_tokens("ЩЁЛК без токенов")

    expected_detail = "invalid token list"
    assert expected_detail in str(error.value), "the error does not name the problem"


@pytest.mark.asyncio
async def test_count_text_tokens_keeps_the_raw_error_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_detail = "user prompt\nsecond line"
    fake_session = FakeSession([FakeResponse({}, status=503, body=private_detail)])
    client = make_client(monkeypatch, fake_session)

    with pytest.raises(LLMAPIError) as error:
        await client.count_text_tokens("private request")

    assert error.value.detail == private_detail, "the error lost the response detail"


@pytest.mark.asyncio
async def test_count_text_tokens_logs_escaped_error_detail(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    private_detail = "secret draft\nnext line"
    fake_session = FakeSession([FakeResponse({}, status=502, body=private_detail)])
    client = make_client(monkeypatch, fake_session)

    with (
        caplog.at_level(logging.ERROR, logger="bot_obormot.services.llm.tokenizer"),
        pytest.raises(LLMAPIError),
    ):
        await client.count_text_tokens("another private request")

    escaped_detail = r"secret draft\nnext line"
    assert escaped_detail in caplog.text, "the log lacks the escaped detail"


@pytest.mark.asyncio
async def test_count_text_tokens_does_not_log_raw_error_detail(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    private_detail = "user prompt\nsecond line"
    fake_session = FakeSession([FakeResponse({}, status=503, body=private_detail)])
    client = make_client(monkeypatch, fake_session)

    with (
        caplog.at_level(logging.ERROR, logger="bot_obormot.services.llm.tokenizer"),
        pytest.raises(LLMAPIError),
    ):
        await client.count_text_tokens("private request")

    assert private_detail not in caplog.text, "the log contains a raw line break"
