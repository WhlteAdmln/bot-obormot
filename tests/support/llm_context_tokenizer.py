# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for llm context tokenizer tests."""

from collections import deque
from dataclasses import replace
from typing import Self

import pytest

from bot_obormot.services.llm import LLMClient
from bot_obormot.settings import Settings


def with_token_counting(settings: Settings, mode: str) -> Settings:
    """Return settings with the requested token counting mode."""
    changes = {"LLM_TOKEN_COUNTING": mode}
    return replace(settings, **changes)


class FakeResponse:
    """Fake response."""

    def __init__(self, payload: object, status: int = 200, body: str = "") -> None:
        """Initializes the test double."""
        self.payload = payload
        self.status = status
        self.body = body

    async def __aenter__(self) -> Self:
        """Enters the async context."""
        return self

    async def __aexit__(
        self, _exc_type: object, _exc: object, _traceback: object
    ) -> bool:
        """Leaves the async context."""
        return False

    async def json(self) -> object:
        """Json."""
        return self.payload

    async def text(self) -> str:
        """Text."""
        return self.body


class FakeSession:
    """Fake session."""

    def __init__(self, responses: object) -> None:
        """Initializes the test double."""
        self.responses = deque(responses)
        self.get_calls = []
        self.post_calls = []

    def get(self, url: str, **kwargs: object) -> "FakeResponse":
        """Get."""
        self.get_calls.append((url, kwargs))
        return self.responses.popleft()

    def post(self, url: str, **kwargs: object) -> "FakeResponse":
        """Post."""
        self.post_calls.append((url, kwargs))
        return self.responses.popleft()


def make_client(
    monkeypatch: pytest.MonkeyPatch,
    fake_session: FakeSession,
    base_url: str = "http://llm.test",
    settings: Settings | None = None,
) -> LLMClient:
    """Build a client with explicit settings and a fake session."""
    if settings is None:
        settings = with_token_counting(Settings(), "llamacpp")

    client = LLMClient(settings=settings)

    async def get_session() -> "FakeSession":
        return fake_session

    monkeypatch.setattr(client, "_get_session", get_session)
    monkeypatch.setattr(client, "_server_url", lambda: base_url)
    return client
