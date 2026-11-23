# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fakes for the chat pipeline dependencies."""

from collections.abc import AsyncIterator, Sequence


class FakePipelineDatabase:
    """Record the pipeline's database calls and return configured values."""

    def __init__(
        self,
        *,
        history_limit: int = 10,
        prune_error: Exception | None = None,
    ) -> None:
        """Store the history limit and the optional pruning failure."""
        self.history_limit = history_limit
        self.prune_error = prune_error
        self.calls: list[tuple[object, ...]] = []

    async def get_system_prompt(self, user_id: int) -> str:
        """Return a fixed system prompt."""
        self.calls.append(("system_prompt", user_id))
        return "system"

    async def get_history_limit(self, user_id: int) -> int:
        """Return the configured history limit."""
        self.calls.append(("history_limit", user_id))
        return self.history_limit

    async def get_history(self, user_id: int, limit: int | None) -> list[object]:
        """Record the requested limit and return a one-message history."""
        self.calls.append(("history", user_id, limit))
        return [{"role": "user", "content": "old"}]

    async def add_exchange(self, *args: object, **kwargs: object) -> None:
        """Record a saved exchange."""
        self.calls.append(("save", args, kwargs))

    async def prune_history(self, user_id: int) -> None:
        """Record pruning or raise the configured failure."""
        self.calls.append(("prune", user_id))
        if self.prune_error is not None:
            raise self.prune_error

    def calls_named(self, name: str) -> list[tuple[object, ...]]:
        """Return the recorded calls with the given name."""
        return [call for call in self.calls if call[0] == name]


class FakePipelineLLM:
    """Stream configured chunks and record the fitted messages."""

    def __init__(self, chunks: Sequence[str]) -> None:
        """Store the chunks to stream."""
        self.chunks = tuple(chunks)
        self.streamed: list[object] = []

    @staticmethod
    async def fit_messages_to_context(**kwargs: object) -> list[object]:
        """Return the fitted messages as one marker."""
        return [kwargs["history"]]

    async def stream(self, messages: object) -> AsyncIterator[str]:
        """Record the messages and yield the configured chunks."""
        self.streamed.append(messages)
        for chunk in self.chunks:
            yield chunk
