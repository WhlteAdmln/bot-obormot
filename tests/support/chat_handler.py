# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Recording collaborators for chat handler tests."""


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
