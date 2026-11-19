# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Final delivery of the complete response to the Telegram user."""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from aiogram.types import Message

from bot_obormot.services.chat.formatting import FormattedChunk, prepare_response
from bot_obormot.services.chat.reply import ReplyTarget
from bot_obormot.services.chat.streaming.sending import (
    UNKNOWN_DELIVERY_ERRORS,
    edit_chunk,
    send_chunk,
)
from bot_obormot.services.chat.streaming.settings import MAX_MESSAGE_LENGTH

logger = logging.getLogger("bot_obormot.handlers.chat")

Preparer = Callable[..., list[FormattedChunk]]
SafeEdit = Callable[..., Awaitable[None]]


@dataclass(frozen=True)
class DeliveryOptions:
    """Configuration for final response formatting and delivery."""

    preparer: Preparer = prepare_response
    max_message_length: int = MAX_MESSAGE_LENGTH
    user_id: int | None = None
    reply_to: ReplyTarget | None = None


_DEFAULT_DELIVERY_OPTIONS: DeliveryOptions = DeliveryOptions()


async def _send_all(
    message: Message,
    chunks: list[FormattedChunk],
    reply_to: ReplyTarget | None,
) -> None:
    """Send chunks; only the first one is linked to the user's message."""
    for number, chunk in enumerate(chunks):
        await send_chunk(
            message,
            chunk,
            reply_to=reply_to if number == 0 else None,
        )


async def deliver_final_response(
    message: Message,
    response: str,
    status: Message | None,
    safe_edit: SafeEdit,
    *,
    options: DeliveryOptions = _DEFAULT_DELIVERY_OPTIONS,
) -> None:
    """Format and deliver the final response.

    The format is detected automatically. A formatting error is retried once
    without ``parse_mode``; network errors are never retried.
    """
    chunks = options.preparer(response, options.max_message_length)

    if not chunks:
        return

    # Send the complete response when streaming was not started.
    if status is None:
        await _send_all(message, chunks, options.reply_to)
        return

    # Replace the last streaming message with the final text. The streaming
    # message was created as a reply, so the link is kept by the edit.
    try:
        await edit_chunk(status, chunks[0], safe_edit)

    except UNKNOWN_DELIVERY_ERRORS:
        # The edit may have been applied; sending again could duplicate it.
        raise

    except Exception:
        logger.warning(
            "Could not finalize streaming response for user_id=%s. "
            "Sending complete response again.",
            options.user_id,
            exc_info=True,
        )

        # Telegram rejected the edit, so the complete response is sent anew.
        await _send_all(message, chunks, options.reply_to)
        return

    await _send_all(message, chunks[1:], None)


__all__ = ["DeliveryOptions", "deliver_final_response"]
