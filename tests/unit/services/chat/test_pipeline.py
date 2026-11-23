# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for chat pipeline."""

from collections.abc import AsyncIterator

import pytest

from bot_obormot.errors import (
    LLMEmptyResponseError,
)
from bot_obormot.services.chat import pipeline as chat_pipeline


@pytest.mark.asyncio
async def test_chat_pipeline_streams_calls_callback_and_persists_exchange() -> None:
    """Chat pipeline streams calls callback and persists exchange."""
    calls = []
    updates = []

    class FakeDatabase:
        async def get_system_prompt(self, user_id: int) -> str:
            calls.append(("system_prompt", user_id))
            return "system"

        async def get_history_limit(self, user_id: int) -> int:
            calls.append(("history_limit", user_id))
            return 12

        async def get_history(self, user_id: int, limit: int | None) -> list[object]:
            calls.append(("history", user_id, limit))
            return [{"role": "user", "content": "old"}]

        async def add_exchange(self, *args: object, **kwargs: object) -> None:
            calls.append(("save", args, kwargs))

        async def prune_history(self, user_id: int) -> None:
            calls.append(("prune", user_id))

    class FakeLLM:
        async def fit_messages_to_context(self, **kwargs: object) -> list[object]:
            calls.append(("fit", kwargs))
            return ["prepared"]

        async def stream(self, messages: object) -> AsyncIterator[str]:
            calls.append(("stream", messages))
            yield "ответ"
            yield " готов"

    async def on_update(text: str) -> None:
        updates.append(text)

    result = await chat_pipeline.process_chat(
        user_id=77,
        user_content="вход",
        saved_user_text="сохранённый вход",
        dependencies=chat_pipeline.ChatPipelineDependencies(
            llm_client=FakeLLM(),
            database=FakeDatabase(),
        ),
        media=[b"image"],
        on_update=on_update,
    )

    assert result == "ответ готов"
    assert updates == ["ответ", "ответ готов"]
    assert calls[-2] == (
        "save",
        (77, "сохранённый вход", "ответ готов"),
        {"media": [b"image"]},
    )
    assert calls[-1] == ("prune", 77)


@pytest.mark.asyncio
async def test_chat_pipeline_caps_history_limit_at_100() -> None:
    """Chat pipeline caps history limit at 100."""
    calls = []

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 500

        async def get_history(self, user_id: int, limit: int | None) -> list[object]:
            calls.append((user_id, limit))
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def prune_history(self, _user_id: object) -> None:
            return None

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            yield "ответ"

    result = await chat_pipeline.process_chat(
        77,
        "вход",
        "вход",
        dependencies=chat_pipeline.ChatPipelineDependencies(
            llm_client=FakeLLM(),
            database=FakeDatabase(),
        ),
    )

    assert result == "ответ"
    assert calls == [(77, 100)]


@pytest.mark.asyncio
async def test_chat_pipeline_keeps_history_limit_below_cap() -> None:
    """Chat pipeline keeps history limit below cap."""
    calls = []

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 17

        async def get_history(
            self, _user_id: object, limit: int | None
        ) -> list[object]:
            calls.append(limit)
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def prune_history(self, _user_id: object) -> None:
            return None

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            yield "ответ"

    result = await chat_pipeline.process_chat(
        77,
        "вход",
        "вход",
        dependencies=chat_pipeline.ChatPipelineDependencies(
            llm_client=FakeLLM(),
            database=FakeDatabase(),
        ),
    )

    assert result == "ответ"
    assert calls == [17]


@pytest.mark.asyncio
async def test_chat_pipeline_does_not_persist_empty_response() -> None:
    """Chat pipeline does not persist empty response."""

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 10

        async def get_history(
            self, _user_id: object, limit: int | None
        ) -> list[object]:
            _ = limit  # Passed by keyword; this fake ignores it.
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            msg = "empty response must not be persisted"
            raise AssertionError(msg)

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            if False:
                yield ""

    with pytest.raises(LLMEmptyResponseError, match="empty response"):
        await chat_pipeline.process_chat(
            77,
            "вход",
            "вход",
            dependencies=chat_pipeline.ChatPipelineDependencies(
                llm_client=FakeLLM(),
                database=FakeDatabase(),
            ),
        )


@pytest.mark.asyncio
async def test_chat_pipeline_returns_response_when_history_pruning_fails() -> None:
    """Chat pipeline returns response when history pruning fails."""

    class FakeDatabase:
        async def get_system_prompt(self, _user_id: object) -> str:
            return "system"

        async def get_history_limit(self, _user_id: object) -> int:
            return 10

        async def get_history(
            self, _user_id: object, limit: int | None
        ) -> list[object]:
            _ = limit  # Passed by keyword; this fake ignores it.
            return []

        async def add_exchange(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def prune_history(self, _user_id: object) -> None:
            msg = "test prune failure"
            raise RuntimeError(msg)

    class FakeLLM:
        async def fit_messages_to_context(self, **_kwargs: object) -> list[object]:
            return []

        async def stream(self, _messages: object) -> AsyncIterator[str]:
            yield "ответ"

    assert (
        await chat_pipeline.process_chat(
            77,
            "вход",
            "вход",
            dependencies=chat_pipeline.ChatPipelineDependencies(
                llm_client=FakeLLM(),
                database=FakeDatabase(),
            ),
        )
        == "ответ"
    )
