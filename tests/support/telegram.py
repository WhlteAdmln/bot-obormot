# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fake aiogram session and Telegram object builders for offline tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from aiogram.client.session.base import BaseSession
from aiogram.types import Chat, Message, Update, User
from typing_extensions import override

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from aiogram.client.bot import Bot
    from aiogram.methods import TelegramMethod
    from aiogram.methods.base import TelegramType

_DEFAULT_MESSAGE_DATE = datetime(2024, 1, 1, tzinfo=UTC)


class FakeTelegramSession(BaseSession):
    """Provide deterministic Telegram API responses without network access."""

    def __init__(
        self,
        responses: Mapping[type[TelegramMethod[Any]], TelegramType] | None = None,
        *,
        stream_data: bytes = b"",
    ) -> None:
        """Create a fake session with method-specific canned responses."""
        super().__init__()
        self.responses = dict(responses or {})
        self.stream_data = stream_data
        self.requests: list[TelegramMethod[TelegramType]] = []
        self.streamed_urls: list[str] = []
        self.closed = False

    @override
    async def close(self) -> None:
        """Mark the fake session as closed."""
        self.closed = True

    @override
    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,
    ) -> TelegramType:
        """Record a Telegram API request and return its configured response."""
        _ = timeout
        self.requests.append(method)
        method_type = type(method)
        if method_type not in self.responses:
            msg = f"No fake response configured for {method_type.__name__}"
            raise AssertionError(msg)

        response = self.responses[method_type]
        if isinstance(response, Message):
            return cast("TelegramType", response.as_(bot))
        return cast("TelegramType", response)

    @override
    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        """Return configured download data in chunks."""
        self.streamed_urls.append(url)
        _ = (headers, timeout, raise_for_status)
        if chunk_size <= 0:
            msg = "Chunk size must be positive"
            raise ValueError(msg)
        for offset in range(0, len(self.stream_data), chunk_size):
            yield self.stream_data[offset : offset + chunk_size]


def make_message(
    *,
    message_id: int = 1,
    chat_id: int = 1,
    user_id: int = 1,
    text: str | None = "Test message",
    date: datetime | None = None,
) -> Message:
    """Create a deterministic Telegram message."""
    return Message(
        message_id=message_id,
        date=date if date is not None else _DEFAULT_MESSAGE_DATE,
        chat=Chat(id=chat_id, type="private"),
        from_user=User(id=user_id, is_bot=False, first_name="Test"),
        text=text,
    )


def make_update(
    *,
    update_id: int = 1,
    message: Message | None = None,
) -> Update:
    """Create a Telegram update containing a message."""
    return Update(
        update_id=update_id,
        message=message if message is not None else make_message(),
    )
