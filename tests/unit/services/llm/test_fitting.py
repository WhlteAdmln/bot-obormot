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
from bot_obormot.services.llm.fitting import ContextFit, fit_messages_to_context
from bot_obormot.settings import Settings


class FakeFittingClient:
    """Fake fitting client."""

    def __init__(
        self,
        context_size: int,
        token_counts: list[int],
        *,
        settings: Settings | None = None,
        counting_mode: str = "llamacpp",
    ) -> None:
        """Initializes the test double."""
        self.settings = settings if settings is not None else Settings()
        self.context_size = context_size
        self.token_counts = deque(token_counts)
        self.counting_mode = counting_mode
        self.count_calls: list[list[dict[str, object]]] = []

    async def get_context_size(self) -> int:
        """Get context size."""
        return self.context_size

    async def get_token_counting_mode(self) -> str:
        """Get token counting mode."""
        return self.counting_mode

    @staticmethod
    def normalize_messages(
        messages: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Normalize messages."""
        return messages

    @staticmethod
    def count_images(messages: list[dict[str, object]]) -> int:
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

    async def count_tokens(self, messages: list[dict[str, object]]) -> int:
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

    expected_contents = [
        "system prompt",
        "recent question",
        "recent answer",
        "current question",
    ]
    contents = [message["content"] for message in result.messages]
    assert contents == expected_contents, "the oldest exchange was not removed"


@pytest.mark.asyncio
async def test_fitting_counts_tokens_once_per_pruning_step() -> None:
    client = FakeFittingClient(
        context_size=12_000,
        token_counts=[11_000, 7_500],
    )
    history = [
        text("user", "first topic"),
        text("assistant", "first reply"),
        text("user", "second topic"),
        text("assistant", "second reply"),
    ]

    await fit_messages_to_context(client, "rules", history, "third topic")

    expected_count = 2
    count_calls = len(client.count_calls)
    assert count_calls == expected_count, "tokens were counted a wrong number of times"


@pytest.mark.asyncio
async def test_fitting_discards_leading_assistant_message() -> None:
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

    expected_roles = ["system", "user", "assistant", "user"]
    roles = [message["role"] for message in result.messages]
    assert roles == expected_roles, "the leading assistant message was kept"


@pytest.mark.asyncio
async def test_fitting_keeps_the_history_length() -> None:
    client = FakeFittingClient(context_size=9_000, token_counts=[250])
    history = [
        text("assistant", "stray reply"),
        text("user", "earlier ask"),
        text("assistant", "earlier reply"),
    ]

    await fit_messages_to_context(client, "persona", history, "new ask")

    expected_count = 3
    assert len(history) == expected_count, "fitting removed messages from the history"


@pytest.mark.asyncio
async def test_fitting_keeps_the_leading_message_in_the_history() -> None:
    client = FakeFittingClient(context_size=11_000, token_counts=[340])
    orphan_content = "dangling assistant text"
    history = [
        text("assistant", orphan_content),
        text("user", "a question before"),
        text("assistant", "an answer before"),
    ]

    await fit_messages_to_context(client, "guide", history, "a question now")

    first_content = history[0]["content"]
    assert first_content == orphan_content, "fitting changed the caller history"


@pytest.mark.asyncio
async def test_fitting_reports_the_prompt_tokens_of_the_fitted_messages() -> None:
    client = FakeFittingClient(context_size=10_000, token_counts=[8_700, 5_430])
    history = [
        text("user", "long gone question"),
        text("assistant", "long gone answer"),
        text("user", "fresh question"),
        text("assistant", "fresh answer"),
    ]

    result = await fit_messages_to_context(client, "tone", history, "what next")

    expected_tokens = 5_430
    assert result.prompt_tokens == expected_tokens, "the prompt tokens are wrong"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("token_counts", "history_roles", "expected_dropped"),
    [
        ([310], ["user", "assistant"], 0),
        ([9_100, 4_200], ["user", "assistant", "user", "assistant"], 2),
        ([9_300, 8_800, 2_600], ["user", "assistant", "user", "assistant"], 4),
        ([270], ["assistant", "user", "assistant"], 1),
        ([9_050, 3_900], ["user", "assistant", "user"], 2),
    ],
)
async def test_fitting_reports_the_dropped_history_messages(
    token_counts: list[int], history_roles: list[str], expected_dropped: int
) -> None:
    client = FakeFittingClient(context_size=10_000, token_counts=token_counts)
    history = [
        text(role, f"{role} line {index}") for index, role in enumerate(history_roles)
    ]

    result = await fit_messages_to_context(client, "manners", history, "latest")

    dropped = result.dropped_history_messages
    assert dropped == expected_dropped, "the dropped history count is wrong"


def _image_history(question: str) -> list[dict[str, object]]:
    return [
        text(
            "user",
            [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,"}},
            ],
        ),
        text("assistant", "old answer"),
        text("user", "recent question"),
        text("assistant", "recent answer"),
    ]


@pytest.mark.asyncio
async def test_fitting_removes_old_exchange_with_an_image() -> None:
    client = FakeFittingClient(
        context_size=10_000,
        token_counts=[6_000, 6_000],
    )
    history = _image_history("old question")

    result = await fit_messages_to_context(
        client,
        "system prompt",
        history,
        "current question",
    )

    expected_contents = [
        "system prompt",
        "recent question",
        "recent answer",
        "current question",
    ]
    contents = [message["content"] for message in result.messages]
    assert contents == expected_contents, "the old image exchange was not removed"


@pytest.mark.parametrize(
    ("call_index", "expected_images"),
    [(0, 1), (1, 0)],
)
@pytest.mark.asyncio
async def test_fitting_recalculates_image_reserve_after_removing_old_exchange(
    call_index: int, expected_images: int
) -> None:
    client = FakeFittingClient(
        context_size=10_500,
        token_counts=[6_200, 6_100],
    )
    history = _image_history("what is on this photo")

    await fit_messages_to_context(client, "assistant rules", history, "and now?")

    images = client.count_images(client.count_calls[call_index])
    assert images == expected_images, "the counted messages have a wrong image count"


@pytest.mark.asyncio
async def test_fitting_rejects_context_smaller_than_reserved_tokens() -> None:
    client = FakeFittingClient(context_size=2_000, token_counts=[])

    with pytest.raises(InputTooLongError, match="Not enough context space"):
        await fit_messages_to_context(client, "system", [], "question")

    expected_empty: list[object] = []
    assert client.count_calls == expected_empty, "tokens were counted without space"


@pytest.mark.asyncio
async def test_fitting_rejects_current_message_that_does_not_fit() -> None:
    client = FakeFittingClient(context_size=10_000, token_counts=[8_000])

    with pytest.raises(InputTooLongError, match="Message is too large"):
        await fit_messages_to_context(client, "system", [], "question")

    expected_count = 1
    count_calls = len(client.count_calls)
    assert count_calls == expected_count, "tokens were counted more than once"


@pytest.mark.asyncio
async def test_fitting_rejects_history_with_unexpected_role_after_pruning() -> None:
    client = FakeFittingClient(context_size=10_000, token_counts=[9_000, 9_000])
    history = [
        text("user", "question"),
        text("system", "unexpected role"),
    ]

    with pytest.raises(LLMUnavailableError) as error:
        await fit_messages_to_context(client, "system", history, "current")

    expected_detail = "expected a user message"
    assert expected_detail in str(error.value), "the error does not name the role"


@pytest.mark.asyncio
async def test_llm_client_method_returns_the_fitted_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient()
    expected = ContextFit(
        messages=[{"role": "system", "content": "be brief"}],
        prompt_tokens=37,
        dropped_history_messages=0,
    )

    async def fake_fit(
        _client: object, _system_prompt: object, _history: object, _message: object
    ) -> ContextFit:
        return expected

    monkeypatch.setattr(client_module, "fit_messages_to_context", fake_fit)

    result = await client.fit_messages_to_context("be brief", [], "hi there")

    assert result is expected, "the method did not return the fitted messages"


@pytest.mark.asyncio
async def test_llm_client_method_delegates_without_changing_public_signature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = LLMClient()
    received: dict[str, object] = {}

    async def fake_fit(
        client_arg: object, system_prompt: object, history: object, user_message: object
    ) -> ContextFit:
        received.update(
            client=client_arg,
            system_prompt=system_prompt,
            history=history,
            user_message=user_message,
        )
        return ContextFit(messages=[], prompt_tokens=12, dropped_history_messages=0)

    monkeypatch.setattr(client_module, "fit_messages_to_context", fake_fit)

    history = [text("user", "old")]
    await client.fit_messages_to_context("system", history, "new")

    expected_arguments = {
        "client": client,
        "system_prompt": "system",
        "history": history,
        "user_message": "new",
    }
    assert received == expected_arguments, "the arguments were not passed through"


def _media_content(image_count: int) -> list[dict[str, object]]:
    image: dict[str, object] = {
        "type": "image_url",
        "image_url": {"url": "data:image/jpeg;base64,"},
    }
    parts: list[dict[str, object]] = [{"type": "text", "text": "Incoming media"}]
    parts.extend(dict(image) for _ in range(image_count))
    return parts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("image_count", "expected_budget"),
    [(1, 27_392), (7, 15_104), (3, 23_296)],
)
async def test_context_fit_log_shows_available_budget(
    image_count: int, expected_budget: int, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeFittingClient(context_size=32_000, token_counts=[100])

    caplog.set_level(logging.INFO, logger="bot_obormot.services.llm.fitting")
    await fit_messages_to_context(client, "system", [], _media_content(image_count))

    budget_detail = f"input_budget={expected_budget}"
    assert budget_detail in caplog.text, "the log lacks the available budget"


@pytest.mark.asyncio
@pytest.mark.parametrize("image_count", [2, 5])
async def test_context_fit_log_shows_context_window(
    image_count: int, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeFittingClient(context_size=32_000, token_counts=[140])

    caplog.set_level(logging.INFO, logger="bot_obormot.services.llm.fitting")
    await fit_messages_to_context(client, "rules", [], _media_content(image_count))

    context_window_detail = "context_window=32000"
    assert context_window_detail in caplog.text, "the log lacks the context window"


@pytest.mark.asyncio
@pytest.mark.parametrize("image_count", [1, 7, 4])
async def test_context_fit_log_shows_image_count(
    image_count: int, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeFittingClient(context_size=32_000, token_counts=[90])

    caplog.set_level(logging.INFO, logger="bot_obormot.services.llm.fitting")
    await fit_messages_to_context(client, "persona", [], _media_content(image_count))

    images_detail = f"images={image_count}"
    assert images_detail in caplog.text, "the log lacks the image count"


@pytest.mark.asyncio
async def test_estimate_mode_uses_larger_safety_margin() -> None:
    settings = replace(Settings(), LLM_MAX_TOKENS=2_048)
    client = FakeFittingClient(
        context_size=10_000,
        token_counts=[6_500],
        settings=settings,
        counting_mode="estimate",
    )

    with pytest.raises(InputTooLongError) as error:
        await fit_messages_to_context(client, "system", [], "question")

    assert error.type is InputTooLongError, "estimate mode accepted the message"
