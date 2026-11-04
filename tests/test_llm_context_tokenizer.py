from collections import deque

import pytest

from bot.config import config
from bot.errors import LLMUnavailableError
from bot.services.llm import LLMClient


class FakeResponse:
    def __init__(self, payload, status=200, body=""):
        self.payload = payload
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def json(self):
        return self.payload

    async def text(self):
        return self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return self.responses.popleft()

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self.responses.popleft()


def attach_session(monkeypatch, client, fake_session, base_url="http://llm.test"):
    async def get_session():
        return fake_session

    monkeypatch.setattr(client, "_get_session", get_session)
    monkeypatch.setattr(client, "_server_url", lambda: base_url)


@pytest.mark.asyncio
async def test_context_size_reads_nested_setting_and_caches_result(monkeypatch):
    fake_session = FakeSession(
        [FakeResponse({"default_generation_settings": {"n_ctx": 8192}})]
    )
    client = LLMClient()
    attach_session(monkeypatch, client, fake_session)

    result = await client.get_context_size()
    cached_result = await client.get_context_size()

    assert result == cached_result == 8192
    assert fake_session.get_calls == [
        ("http://llm.test/props", {"params": {"model": config.LLM_MODEL}})
    ]


@pytest.mark.asyncio
async def test_context_size_rejects_boolean_value(monkeypatch):
    fake_session = FakeSession([FakeResponse({"n_ctx": True})])
    client = LLMClient()
    attach_session(monkeypatch, client, fake_session)

    with pytest.raises(LLMUnavailableError, match="invalid n_ctx"):
        await client.get_context_size()

    assert client._context_size is None


@pytest.mark.asyncio
async def test_count_tokens_applies_template_then_tokenizes(monkeypatch):
    fake_session = FakeSession(
        [
            FakeResponse({"prompt": "rendered prompt"}),
            FakeResponse({"tokens": [1, 2, 3, 4]}),
        ]
    )
    client = LLMClient()
    attach_session(monkeypatch, client, fake_session)
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

    assert result == 4
    assert [call[0] for call in fake_session.post_calls] == [
        "http://llm.test/apply-template",
        "http://llm.test/tokenize",
    ]
    apply_payload = fake_session.post_calls[0][1]["json"]
    assert apply_payload["model"] == config.LLM_MODEL
    assert apply_payload["add_generation_prompt"] is True
    image_part = apply_payload["messages"][0]["content"][0]
    assert image_part["image_url"]["url"] == "data:image/jpeg;base64,"
    assert messages[0]["content"][0]["image_url"]["url"].endswith("PRIVATE")

    tokenize_payload = fake_session.post_calls[1][1]["json"]
    assert tokenize_payload == {
        "model": config.LLM_MODEL,
        "content": "rendered prompt",
        "add_special": True,
        "parse_special": True,
    }


@pytest.mark.asyncio
async def test_count_tokens_rejects_invalid_normalized_content(monkeypatch):
    fake_session = FakeSession([])
    client = LLMClient()
    attach_session(monkeypatch, client, fake_session)
    monkeypatch.setattr(
        client,
        "_normalize_messages",
        lambda messages: [{"role": "user", "content": 123}],
    )

    with pytest.raises(LLMUnavailableError, match="Invalid message content"):
        await client.count_tokens([{"role": "user", "content": "hello"}])

    assert fake_session.post_calls == []


@pytest.mark.asyncio
async def test_count_text_tokens_sends_expected_payload(monkeypatch):
    fake_session = FakeSession([FakeResponse({"tokens": [1, 2, 3]})])
    client = LLMClient()
    attach_session(monkeypatch, client, fake_session)

    result = await client.count_text_tokens("Привет")

    assert result == 3
    assert fake_session.post_calls == [
        (
            "http://llm.test/tokenize",
            {
                "json": {
                    "model": config.LLM_MODEL,
                    "content": "Привет",
                    "add_special": False,
                    "parse_special": True,
                }
            },
        )
    ]


@pytest.mark.asyncio
async def test_count_text_tokens_empty_text_skips_http(monkeypatch):
    client = LLMClient()

    async def unexpected_session():
        raise AssertionError("HTTP session must not be requested for empty text")

    monkeypatch.setattr(client, "_get_session", unexpected_session)

    assert await client.count_text_tokens("") == 0


@pytest.mark.asyncio
async def test_count_text_tokens_rejects_invalid_token_list(monkeypatch):
    fake_session = FakeSession([FakeResponse({"tokens": "not-a-list"})])
    client = LLMClient()
    attach_session(monkeypatch, client, fake_session)

    with pytest.raises(LLMUnavailableError, match="invalid token list"):
        await client.count_text_tokens("hello")
