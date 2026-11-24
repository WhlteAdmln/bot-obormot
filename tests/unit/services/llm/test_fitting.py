# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for llm fitting."""

import logging
from collections import deque
from copy import deepcopy
from dataclasses import replace

import pytest

from bot_obormot.errors import InputTooLongError, LLMUnavailableError
from bot_obormot.services.llm import LLMClient
from bot_obormot.services.llm import client as client_module
from bot_obormot.services.llm.fitting import fit_messages_to_context
from bot_obormot.settings import Settings


class FakeFittingClient:
    """Fake fitting client."""

    def __init__(
        self,
        context_size: object,
        token_counts: object,
        *,
        settings: Settings | None = None,
    ) -> None:
        """Initializes the test double."""
        self.settings = settings if settings is not None else Settings()
        self.context_size = context_size
        self.token_counts = deque(token_counts)
        self.count_calls = []

    async def get_context_size(self) -> int | None:
        """Get context size."""
        return self.context_size

    @staticmethod
    async def get_token_counting_mode() -> str:
        """Get token counting mode."""
        return "llamacpp"

    @staticmethod
    def normalize_messages(messages: object) -> list[dict[str, object]]:
        """Normalize messages."""
        return messages

    @staticmethod
    def count_images(messages: object) -> int:
        """Count images."""
        count = 0
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                expected_get = "image_url"
                count += sum(
                    1
                    for part in content
                    if isinstance(part, dict) and part.get("type") == expected_get
                )
        return count

    async def count_tokens(self, messages: object) -> int:
        """Count tokens."""
        self.count_calls.append(deepcopy(messages))
        return self.token_counts.popleft()


def text(role: str, content: object) -> dict[str, object]:
    """Text."""
    return {"role": role, "content": content}


@pytest.mark.asyncio
async def test_fitting_removes_oldest_complete_exchange_and_keeps_recent_history() -> (
    None
):
    client = FakeFittingClient(
        context_size=10_000,
        token_counts=[9_000, 6_000],
    )
    history = [
        text("user", "old question"),
        text("assistant", "old answer"),
        text("user", "recent question"),
        text("assistant", "recent answer"),
    ]

    result = await fit_messages_to_context(
        client,
        "system prompt",
        history,
        "current question",
    )

    assert [message["content"] for message in result] == [
        "system prompt",
        "recent question",
        "recent answer",
        "current question",
    ]
    expected_count = 2
    assert len(client.count_calls) == expected_count


@pytest.mark.asyncio
async def test_fitting_discards_leading_assistant_and_does_not_mutate_history() -> None:
    client = FakeFittingClient(context_size=10_000, token_counts=[100])
    history = [
        text("assistant", "orphan answer"),
        text("user", "previous question"),
        text("assistant", "previous answer"),
    ]

    result = await fit_messages_to_context(
        client,
        "system prompt",
        history,
        "current question",
    )

    assert [message["role"] for message in result] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    expected_count = 3
    assert len(history) == expected_count
    expected_content = "orphan answer"
    assert history[0]["content"] == expected_content


@pytest.mark.asyncio
async def test_fitting_recalculates_image_reserve_after_removing_old_exchange() -> None:
    client = FakeFittingClient(
        context_size=10_000,
        token_counts=[6_000, 6_000],
    )
    history = [
        text(
            "user",
            [
                {"type": "text", "text": "old question"},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,"}},
            ],
        ),
        text("assistant", "old answer"),
        text("user", "recent question"),
        text("assistant", "recent answer"),
    ]

    result = await fit_messages_to_context(
        client,
        "system prompt",
        history,
        "current question",
    )

    assert [message["content"] for message in result] == [
        "system prompt",
        "recent question",
        "recent answer",
        "current question",
    ]
    assert client.count_images(client.count_calls[0]) == 1
    assert client.count_images(client.count_calls[1]) == 0


@pytest.mark.asyncio
async def test_fitting_rejects_context_smaller_than_reserved_tokens() -> None:
    client = FakeFittingClient(context_size=2_000, token_counts=[])

    with pytest.raises(InputTooLongError, match="Not enough context space"):
        await fit_messages_to_context(client, "system", [], "question")

    expected_empty = []
    assert client.count_calls == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_fitting_rejects_current_message_that_does_not_fit() -> None:
    client = FakeFittingClient(context_size=10_000, token_counts=[8_000])

    with pytest.raises(InputTooLongError, match="Message is too large"):
        await fit_messages_to_context(client, "system", [], "question")

    assert len(client.count_calls) == 1


@pytest.mark.asyncio
async def test_fitting_rejects_history_with_unexpected_role_after_pruning() -> None:
    client = FakeFittingClient(context_size=10_000, token_counts=[9_000, 9_000])
    history = [
        text("user", "question"),
        text("system", "unexpected role"),
    ]

    with pytest.raises(LLMUnavailableError, match="expected a user message"):
        await fit_messages_to_context(client, "system", history, "current")


@pytest.mark.asyncio
async def test_llm_client_method_delegates_without_changing_public_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient()
    expected = [{"role": "system", "content": "system"}]
    received = {}

    async def fake_fit(
        client_arg: object, system_prompt: object, history: object, user_message: object
    ) -> list[dict[str, object]]:
        received.update(
            client=client_arg,
            system_prompt=system_prompt,
            history=history,
            user_message=user_message,
        )
        return expected

    monkeypatch.setattr(client_module, "fit_messages_to_context", fake_fit)

    history = [text("user", "old")]
    result = await client.fit_messages_to_context("system", history, "new")

    assert result is expected
    assert received == {
        "client": client,
        "system_prompt": "system",
        "history": history,
        "user_message": "new",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_count", "expected_budget"),
    [(1, 27_392), (7, 15_104), (3, 23_296)],
)
async def test_context_fit_log_distinguishes_window_from_available_budget(
    image_count: int, expected_budget: int, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeFittingClient(context_size=32_000, token_counts=[100])
    content = [
        {"type": "text", "text": "Incoming media"},
        *[
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,"}}
            for _ in range(image_count)
        ],
    ]

    caplog.set_level(logging.INFO, logger="bot_obormot.services.llm.fitting")
    await fit_messages_to_context(client, "system", [], content)

    assert f"input_budget={expected_budget}" in caplog.text
    context_window_detail = "context_window=32000"
    assert context_window_detail in caplog.text
    assert f"images={image_count}" in caplog.text


@pytest.mark.asyncio
async def test_estimate_mode_uses_larger_safety_margin() -> None:
    settings = replace(Settings(), LLM_MAX_TOKENS=2_048)
    client = FakeFittingClient(
        context_size=10_000,
        token_counts=[6_500],
        settings=settings,
    )

    async def estimate_mode() -> str:
        return "estimate"

    client.get_token_counting_mode = estimate_mode
    with pytest.raises(InputTooLongError):
        await fit_messages_to_context(client, "system", [], "question")
