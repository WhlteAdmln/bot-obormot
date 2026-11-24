# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for handlers split tests."""

from types import SimpleNamespace

from tests.support.settings import make_settings

SETTINGS = make_settings()


class FakeMessage:
    """Fake message."""

    def __init__(self, user_id: int | None, text: str = "") -> None:
        """Initializes the test double; ``None`` means a message without sender."""
        self.from_user = None if user_id is None else SimpleNamespace(id=user_id)
        self.text = text
        self.answers = []

    async def answer(self, text: str, **_kwargs: object) -> None:
        """Answer."""
        self.answers.append(text)
