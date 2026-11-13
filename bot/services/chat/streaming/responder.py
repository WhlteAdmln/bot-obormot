# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Состояние и обновление промежуточного Telegram-ответа."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.types import Message

from bot.services.chat.formatting import format_roleplay, split_formatted_message
from bot.services.chat.streaming.settings import (
    MAX_MESSAGE_LENGTH,
    STREAM_TOKEN_THRESHOLD,
    STREAM_UPDATE_INTERVAL,
)

logger = logging.getLogger("bot.handlers.chat")

TokenCounter = Callable[[str], Awaitable[int]]
SafeEdit = Callable[[Any, str], Awaitable[None]]
Formatter = Callable[[str], str]
Splitter = Callable[..., list[str]]


class StreamingResponder:
    """Управляет промежуточным сообщением во время генерации LLM.

    Состояние явно хранится в атрибутах вместо локальных переменных
    замыкания и пяти `nonlocal`.
    """

    def __init__(
        self,
        message: Message,
        user_id: int,
        count_text_tokens: TokenCounter,
        safe_edit: SafeEdit,
        *,
        formatter: Formatter = format_roleplay,
        splitter: Splitter = split_formatted_message,
        token_threshold: int = STREAM_TOKEN_THRESHOLD,
        update_interval: float = STREAM_UPDATE_INTERVAL,
        max_message_length: int = MAX_MESSAGE_LENGTH,
    ) -> None:
        """Stores the dependencies and the initial streaming state."""
        self.message = message
        self.user_id = user_id
        self.count_text_tokens = count_text_tokens
        self.safe_edit = safe_edit
        self.formatter = formatter
        self.splitter = splitter
        self.token_threshold = token_threshold
        self.update_interval = update_interval
        self.max_message_length = max_message_length

        self.status: Message | None = None
        self.streaming_failed = False
        self.last_update = 0.0
        self.next_token_check_chars = 300
        self.last_displayed_text: str | None = None

    async def on_update(self, current_text: str) -> None:
        """Обновляет промежуточный ответ, если выполнены исходные пороги."""
        if self.streaming_failed:
            return

        now = asyncio.get_running_loop().time()

        # Пока сообщение не создано, проверяем порог независимо от
        # интервала обновления Telegram.
        if self.status is None:
            if len(current_text) < self.next_token_check_chars:
                return

            # Следующая проверка после дополнительных символов.
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

        # После создания сообщения обновляем его не чаще исходного интервала.
        if now - self.last_update < self.update_interval:
            return

        await self._update_streaming_display(current_text)

    async def _start_streaming_display(self, current_text: str) -> None:
        """Creates the initial streaming message."""
        try:
            formatted_text = self.formatter(current_text)
            chunks = self.splitter(
                formatted_text,
                max_length=self.max_message_length,
            )

            if not chunks:
                return

            self.status = await self.message.answer(
                chunks[0],
                parse_mode="HTML",
            )

            self.last_displayed_text = chunks[0]
            self.last_update = asyncio.get_running_loop().time()

        except Exception:
            self.streaming_failed = True
            logger.warning(
                "Could not start streaming display for user_id=%s",
                self.user_id,
                exc_info=True,
            )

    async def _update_streaming_display(self, current_text: str) -> None:
        """Updates the existing streaming message."""
        try:
            formatted_text = self.formatter(current_text)
            chunks = self.splitter(
                formatted_text,
                max_length=self.max_message_length,
            )

            if not chunks:
                return

            first_chunk = chunks[0]

            if first_chunk != self.last_displayed_text:
                await self.safe_edit(self.status, first_chunk)
                self.last_displayed_text = first_chunk

            self.last_update = asyncio.get_running_loop().time()

        except Exception:
            self.streaming_failed = True
            logger.warning(
                "Streaming message update failed for user_id=%s",
                self.user_id,
                exc_info=True,
            )

    async def cancel(self) -> None:
        """Отмечает промежуточное сообщение как отменённое."""
        if self.status is None:
            return

        try:
            await asyncio.shield(
                self.safe_edit(
                    self.status,
                    "⏹ Запрос отменён.",
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


__all__ = ["StreamingResponder"]
