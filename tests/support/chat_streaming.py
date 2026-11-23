# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Shared helpers for chat streaming tests."""

from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.methods import GetMe


class FakeMessage:
    """Fake message."""

    def __init__(self) -> None:
        """Initializes the test double."""
        self.answers = []

    async def answer(self, text: str, **kwargs: object) -> SimpleNamespace:
        """Answer."""
        self.answers.append((text, kwargs))
        return SimpleNamespace(text=text)


def split_text(text: str, *, max_length: object) -> list[object]:
    return [
        text[index : index + max_length] for index in range(0, len(text), max_length)
    ]


PARSE_ERROR = "Bad Request: can't parse entities: Can't find end of the entity"


def bad_request(text: str) -> TelegramBadRequest:
    return TelegramBadRequest(method=GetMe(), message=text)


def network_error() -> TelegramNetworkError:
    return TelegramNetworkError(method=GetMe(), message="timeout")


class FakeReplyMessage:
    def __init__(
        self,
        text: str = "x",
        message_id: int | None = 1,
        failures: list[Exception | None] | None = None,
    ) -> None:
        self.text = text
        self.message_id = message_id
        self.chat = SimpleNamespace(id=5)
        self.from_user = SimpleNamespace(id=9)
        self.answers: list[tuple[str, dict[str, object]]] = []
        self.failures = list(failures or [])

    async def answer(self, text: str, **kwargs: object) -> SimpleNamespace:
        self.answers.append((text, kwargs))
        if self.failures:
            failure = self.failures.pop(0)
            if failure is not None:
                raise failure
        return SimpleNamespace(text=text)


async def edit_status(
    _status: object, _text: str, parse_mode: str | None = None
) -> None:
    del parse_mode
