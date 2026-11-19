# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Send and edit formatted messages with the safe plain-text fallback."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramNetworkError,
    TelegramServerError,
)

if TYPE_CHECKING:
    from aiogram.types import Message

    from bot_obormot.services.chat.formatting import FormattedChunk
    from bot_obormot.services.chat.reply import ReplyTarget

logger = logging.getLogger("bot_obormot.handlers.chat")

SafeEdit = Callable[..., Awaitable[None]]

# Delivery of such requests is unknown: they must never be repeated blindly.
UNKNOWN_DELIVERY_ERRORS = (TelegramNetworkError, TelegramServerError)

_ENTITY_ERROR_MARKERS = ("can't parse entities", "can't find end of")


def is_entity_parse_error(error: BaseException) -> bool:
    """Return True only for a confirmed Telegram formatting error."""
    return isinstance(error, TelegramBadRequest) and any(
        marker in str(error).lower() for marker in _ENTITY_ERROR_MARKERS
    )


def _send_kwargs(
    parse_mode: str | None,
    reply_to: ReplyTarget | None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    if parse_mode is not None:
        kwargs["parse_mode"] = parse_mode

    reply_parameters = reply_to.parameters() if reply_to is not None else None
    if reply_parameters is not None:
        kwargs["reply_parameters"] = reply_parameters

    return kwargs


async def send_chunk(
    message: Message,
    chunk: FormattedChunk,
    *,
    reply_to: ReplyTarget | None = None,
) -> Message:
    """Send one chunk; retry once without ``parse_mode`` on a parse error.

    The retry uses the original LLM text and the same ``reply_parameters``.
    """
    try:
        return await message.answer(
            chunk.text,
            **_send_kwargs(chunk.parse_mode, reply_to),
        )
    except TelegramBadRequest as error:
        if chunk.parse_mode is None or not is_entity_parse_error(error):
            raise

        logger.warning(
            "Telegram rejected %s formatting: %s. Retrying without parse_mode.",
            chunk.parse_mode,
            error,
        )

    try:
        return await message.answer(
            chunk.plain_text,
            **_send_kwargs(None, reply_to),
        )
    except Exception:
        logger.exception("Plain-text retry failed after a formatting error")
        raise


async def edit_chunk(
    status: Message,
    chunk: FormattedChunk,
    safe_edit: SafeEdit,
) -> None:
    """Edit a message; retry once without ``parse_mode`` on a parse error."""
    try:
        await safe_edit(status, chunk.text, parse_mode=chunk.parse_mode)
        return
    except TelegramBadRequest as error:
        if chunk.parse_mode is None or not is_entity_parse_error(error):
            raise

        logger.warning(
            "Telegram rejected %s formatting while editing: %s. "
            "Retrying without parse_mode.",
            chunk.parse_mode,
            error,
        )

    try:
        await safe_edit(status, chunk.plain_text, parse_mode=None)
    except Exception:
        logger.exception("Plain-text edit retry failed after a formatting error")
        raise


__all__ = [
    "UNKNOWN_DELIVERY_ERRORS",
    "edit_chunk",
    "is_entity_parse_error",
    "send_chunk",
]
