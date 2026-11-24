# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fake aiogram FSM context for offline tests."""

from collections.abc import Mapping


class FakeFSMContext:
    """Keep FSM data and the current state in memory like aiogram's FSMContext."""

    def __init__(
        self,
        data: Mapping[str, object] | None = None,
        current_state: str | None = None,
    ) -> None:
        """Create a context with initial data and an optional current state."""
        self.data: dict[str, object] = dict(data or {})
        self.current_state = current_state

    async def get_data(self) -> dict[str, object]:
        """Return a copy of the stored data."""
        return dict(self.data)

    async def update_data(self, **kwargs: object) -> dict[str, object]:
        """Merge new values into the stored data and return the result."""
        self.data.update(kwargs)
        return dict(self.data)

    async def get_state(self) -> str | None:
        """Return the current state name."""
        return self.current_state
