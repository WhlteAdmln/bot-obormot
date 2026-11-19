# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Association between an incoming message and the bot's reply."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.types import ReplyParameters


@dataclass(frozen=True, slots=True)
class ReplyTarget:
    """The incoming message that an LLM response must be linked to.

    One instance is created per LLM request, so the association does not
    depend on the order in which responses are completed. When several user
    messages are combined into one request, the target is the last one.
    """

    chat_id: int | None = None
    message_id: int | None = None

    @classmethod
    def from_message(cls, message: Any) -> ReplyTarget:  # noqa: ANN401 - aiogram Message or a test double
        """Store ``chat_id`` and ``message_id`` of an incoming message."""
        chat = getattr(message, "chat", None)
        chat_id = getattr(chat, "id", None)
        message_id = getattr(message, "message_id", None)
        return cls(
            chat_id=chat_id if isinstance(chat_id, int) else None,
            message_id=message_id if isinstance(message_id, int) else None,
        )

    def parameters(self) -> ReplyParameters | None:
        """Return ``reply_parameters`` for ``sendMessage`` or None.

        ``allow_sending_without_reply`` lets Telegram deliver the response
        when the original message is no longer available.
        """
        if self.message_id is None:
            return None

        return ReplyParameters(
            message_id=self.message_id,
            allow_sending_without_reply=True,
        )


__all__ = ["ReplyTarget"]
