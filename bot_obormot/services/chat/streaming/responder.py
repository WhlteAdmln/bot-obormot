# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Manage the state and updates of an intermediate Telegram response."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from aiogram.types import Message

from bot_obormot.services.chat.formatting import split_plain_message
from bot_obormot.services.chat.reply import ReplyTarget
from bot_obormot.services.chat.streaming.settings import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
)
from bot_obormot.services.chat.streaming.texts import REQUEST_CANCELLED_TEXT

if TYPE_CHECKING:
    from bot_obormot.services.chat.streaming.sending import AnswerOptions

logger = logging.getLogger("bot_obormot.handlers.chat")

TokenCounter = Callable[[str], Awaitable[int]]
SafeEdit = Callable[..., Awaitable[None]]
Splitter = Callable[..., list[str]]


@dataclass(frozen=True)
class StreamingResponderOptions:
    """Configuration for streaming display thresholds and formatting."""

    splitter: Splitter = split_plain_message
    token_threshold: int = STREAM_TOKEN_THRESHOLD
    update_interval: float = STREAM_UPDATE_INTERVAL
    max_message_length: int = MAX_MESSAGE_LENGTH


_DEFAULT_STREAMING_RESPONDER_OPTIONS: StreamingResponderOptions = (
    StreamingResponderOptions()
)


class StreamingResponder:  # pylint: disable=too-many-instance-attributes  # reply state
    """Manage the intermediate message during LLM generation.

    State is explicitly stored in attributes instead of closure-local
    variables and five ``nonlocal`` declarations.
    """

    def __init__(
        self,
        message: Message,
        user_id: int,
        count_text_tokens: TokenCounter,
        safe_edit: SafeEdit,
        *,
        reply_to: ReplyTarget | None = None,
        options: StreamingResponderOptions = _DEFAULT_STREAMING_RESPONDER_OPTIONS,
    ) -> None:
        """Store the dependencies and the initial streaming state."""
        self.message = message
        self.user_id = user_id
        self.count_text_tokens = count_text_tokens
        self.safe_edit = safe_edit
        self.reply_to = reply_to
        self.splitter = options.splitter
        self.token_threshold = options.token_threshold
        self.update_interval = options.update_interval
        self.max_message_length = options.max_message_length

        self.status: Message | None = None
        self.streaming_failed = False
        self.last_update = 0.0
        self.next_token_check_chars = 300
        self.last_displayed_text: str | None = None

    async def on_update(self, current_text: str) -> None:
        """Update the intermediate response when the original thresholds are met."""
        if self.streaming_failed:
            return

        now = asyncio.get_running_loop().time()

        # Before the message is created, check the threshold independently
        # of the Telegram update interval.
        if self.status is None:
            if len(current_text) < self.next_token_check_chars:
                return

            # Schedule the next check after additional characters.
            self.next_token_check_chars = len(current_text) + 128

            try:
                token_count = await self.count_text_tokens(current_text)
            except Exception:
                logger.warning(
                    "Could not count streaming tokens for user_id=%s",
                    self.user_id,
                    exc_info=True,
                )
                return

            if token_count <= self.token_threshold:
                return

            await self._start_streaming_display(current_text)
            return

        # After creation, update the message no more often than the original interval.
        if now - self.last_update < self.update_interval:
            return

        await self._update_streaming_display(current_text)

    async def _start_streaming_display(self, current_text: str) -> None:
        """Create the initial streaming message."""
        try:
            await self._send_first_chunk(current_text)

        except Exception:
            self.streaming_failed = True
            logger.warning(
                "Could not start streaming display for user_id=%s",
                self.user_id,
                exc_info=True,
            )

    async def _send_first_chunk(self, current_text: str) -> None:
        """Answer with the first chunk of the text generated so far."""
        # The text is shown as is while it is generated: incomplete
        # markup cannot be parsed reliably, the format is detected at
        # the end.
        chunks = self.splitter(
            current_text,
            max_length=self.max_message_length,
        )

        if not chunks:
            return

        reply_parameters = (
            self.reply_to.parameters() if self.reply_to is not None else None
        )
        kwargs: AnswerOptions = {}
        if reply_parameters is not None:
            kwargs["reply_parameters"] = reply_parameters

        self.status = await self.message.answer(chunks[0], **kwargs)

        self.last_displayed_text = chunks[0]
        self.last_update = asyncio.get_running_loop().time()

    async def _update_streaming_display(self, current_text: str) -> None:
        """Update the existing streaming message."""
        try:
            await self._edit_first_chunk(current_text)

        except Exception:
            self.streaming_failed = True
            logger.warning(
                "Streaming message update failed for user_id=%s",
                self.user_id,
                exc_info=True,
            )

    async def _edit_first_chunk(self, current_text: str) -> None:
        """Edit the status message when the first chunk has changed."""
        # The text is shown as is while it is generated: incomplete
        # markup cannot be parsed reliably, the format is detected at
        # the end.
        chunks = self.splitter(
            current_text,
            max_length=self.max_message_length,
        )

        if not chunks:
            return

        first_chunk = chunks[0]

        if first_chunk != self.last_displayed_text:
            await self.safe_edit(self.status, first_chunk, parse_mode=None)
            self.last_displayed_text = first_chunk

        self.last_update = asyncio.get_running_loop().time()

    async def cancel(self) -> None:
        """Mark the intermediate message as cancelled."""
        if self.status is None:
            return

        try:
            await asyncio.shield(
                self.safe_edit(
                    self.status,
                    REQUEST_CANCELLED_TEXT,
                )
            )

        except asyncio.CancelledError:
            logger.debug(
                "Status update was cancelled",
                exc_info=True,
            )

        except Exception:
            logger.debug(
                "Could not update status after cancellation",
                exc_info=True,
            )


__all__ = ["StreamingResponder", "StreamingResponderOptions"]
