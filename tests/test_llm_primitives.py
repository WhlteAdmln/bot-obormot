import json

import pytest

from bot.config import config
from bot.errors import LLMUnavailableError
from bot.services.llm import LLMClient, llm_client
from bot.services.llm import endpoints, messages, session


def test_llm_package_preserves_public_imports():
    assert isinstance(llm_client, LLMClient)
    assert callable(llm_client.count_tokens)
    assert callable(llm_client.fit_messages_to_context)
    assert callable(llm_client.stream)


def test_normalize_content_preserves_supported_shapes():
    assert messages.normalize_content(None) == ""
    assert messages.normalize_content("hello") == "hello"
    assert messages.normalize_content(["text", {"type": "image_url"}, 7]) == [
        "text",
        {"type": "image_url"},
        "7",
    ]
    assert json.loads(messages.normalize_content({"ключ": "значение"})) == {
        "ключ": "значение"
    }


def test_normalize_messages_preserves_extra_fields_and_normalizes_content():
    result = messages.normalize_messages(
        [{"role": "user", "content": None, "name": "client"}]
    )

    assert result == [{"role": "user", "content": "", "name": "client"}]


@pytest.mark.parametrize(
    "payload",
    [
        ["not-a-message"],
        [{"role": 123, "content": "hello"}],
    ],
)
def test_normalize_messages_rejects_invalid_structure(payload):
    with pytest.raises(LLMUnavailableError):
        messages.normalize_messages(payload)


def test_prepare_messages_for_count_removes_image_payload_without_mutating_input():
    original = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,SECRET"},
                },
                {"type": "text", "text": "описание"},
                "plain-part",
            ],
        }
    ]

    prepared = messages.prepare_messages_for_count(original)

    assert prepared[0]["content"][0]["image_url"]["url"] == "data:image/jpeg;base64,"
    assert original[0]["content"][0]["image_url"]["url"].endswith("SECRET")
    assert prepared[0]["content"][1:] == original[0]["content"][1:]


def test_count_images_counts_only_image_url_parts():
    assert (
        messages.count_images(
            [
                {"content": [{"type": "image_url"}, {"type": "text"}]},
                {"content": "plain text"},
                {"content": [{"type": "image_url"}]},
            ]
        )
        == 2
    )


def test_server_url_removes_trailing_slashes_and_v1(monkeypatch):
    monkeypatch.setattr(config, "LLM_BASE_URL", "http://localhost:8080/v1///")
    assert endpoints.server_url() == "http://localhost:8080"


@pytest.mark.asyncio
async def test_get_session_reuses_open_session_and_recreates_closed_one(monkeypatch):
    created = []

    class FakeSession:
        def __init__(self, timeout):
            self.timeout = timeout
            self.closed = False
            created.append(self)

    monkeypatch.setattr(session.aiohttp, "ClientSession", FakeSession)
    monkeypatch.setattr(session.aiohttp, "ClientTimeout", lambda total: total)
    monkeypatch.setattr(config, "LLM_TIMEOUT", 12)

    class Client:
        session = None

    client = Client()
    first = await session.get_session(client)
    second = await session.get_session(client)

    assert first is second
    assert first.timeout == 12
    assert len(created) == 1

    first.closed = True
    third = await session.get_session(client)

    assert third is not first
    assert len(created) == 2
