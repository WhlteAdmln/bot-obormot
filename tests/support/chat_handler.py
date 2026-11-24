# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Recording collaborators for chat handler tests."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class RecordingAggregator:
    """Return a configured aggregation result and record each call."""

    def __init__(self, calls: list[object]) -> None:
        """Share the call log and start with a non-empty result."""
        self.calls = calls
        self.result: str | None = "входящий текст"

    async def collect(self, _message: object) -> str | None:
        """Record the call and return the configured result."""
        self.calls.append("aggregate")
        return self.result


class RecordingTokenCounter:
    """Count every text as the same number of tokens and record each call."""

    def __init__(self, calls: list[object]) -> None:
        """Share the call log."""
        self.calls = calls

    async def count_text_tokens(self, _text: str) -> int:
        """Record the call and return a fixed count."""
        self.calls.append("count-tokens")
        return 151


class RecordingUserLocks:
    """Report a configured number of pending requests and record each hold."""

    def __init__(self, calls: list[object]) -> None:
        """Share the call log and start with no pending requests."""
        self.calls = calls
        self.pending_count = 0
        self.entered = asyncio.Event()

    def pending(self, _user_id: int) -> int:
        """Return the configured number of pending requests."""
        return self.pending_count

    @asynccontextmanager
    async def hold(self, _user_id: int) -> AsyncIterator[None]:
        """Record entering and leaving the lock."""
        self.calls.append("lock-enter")
        self.entered.set()
        try:
            yield
        finally:
            self.calls.append("lock-exit")
