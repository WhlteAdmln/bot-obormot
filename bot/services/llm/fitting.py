# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Подбор истории сообщений под доступное контекстное окно LLM."""

import logging
import math
from typing import Any, Protocol

from bot.config import config
from bot.errors import InputTooLongError, LLMUnavailableError
from bot.services.llm.constants import (
    CONTEXT_SAFETY_MARGIN,
    ESTIMATE_CONTEXT_SAFETY_FACTOR,
    IMAGE_TOKEN_RESERVE,
)

logger = logging.getLogger(__name__)

# The system prompt and the current user message are always kept.
_PINNED_MESSAGES = 2


class FittingClient(Protocol):
    """Минимальный интерфейс клиента, необходимый для fitting истории."""

    async def get_context_size(self) -> int:
        """Returns the context window size of the model."""

    def _normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    @staticmethod
    def _count_images(messages: list[dict[str, Any]]) -> int: ...

    async def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Counts the prompt tokens of the messages."""

    async def get_token_counting_mode(self) -> str:
        """Returns the selected token counting mode."""


async def fit_messages_to_context(
    client: FittingClient,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_message: object,
) -> list[dict[str, Any]]:
    """Подбирает максимально возможную историю под контекст модели."""
    context_size = await client.get_context_size()
    counting_mode = await client.get_token_counting_mode()
    safety_margin = CONTEXT_SAFETY_MARGIN
    if counting_mode == "estimate":
        safety_margin += math.ceil(context_size * ESTIMATE_CONTEXT_SAFETY_FACTOR)

    history = list(history)

    # История должна начинаться с пользовательского сообщения.
    while history and history[0].get("role") != "user":
        history.pop(0)

    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_message},
    ]

    messages = client._normalize_messages(messages)

    while True:
        # Число изображений меняется при удалении старых обменов.
        image_count = client._count_images(messages)

        image_reserved_tokens = IMAGE_TOKEN_RESERVE * image_count
        reserved_tokens = config.LLM_MAX_TOKENS + safety_margin + image_reserved_tokens

        available_tokens = context_size - reserved_tokens

        if available_tokens <= 0:
            msg = "Недостаточно места в контексте для запроса."
            raise InputTooLongError(msg)

        token_count = await client.count_tokens(messages)

        if token_count <= available_tokens:
            logger.info(
                (
                    "Context fit: prompt_tokens=%s, input_budget=%s, "
                    "context_window=%s, output_reserve=%s, safety_margin=%s, "
                    "images=%s, image_reserve=%s, history_messages=%s"
                ),
                token_count,
                available_tokens,
                context_size,
                config.LLM_MAX_TOKENS,
                safety_margin,
                image_count,
                image_reserved_tokens,
                len(messages) - _PINNED_MESSAGES,
            )
            return messages

        # В списке остаются только system и текущий user:
        # даже они не помещаются в доступный контекст.
        if len(messages) <= _PINNED_MESSAGES:
            msg = "Сообщение слишком большое для контекста модели."
            raise InputTooLongError(msg)

        # История должна быть организована парами user/assistant.
        if messages[1].get("role") != "user":
            msg = "Invalid history: expected a user message"
            raise LLMUnavailableError(msg)

        # Удаляем старейшее пользовательское сообщение.
        messages.pop(1)

        # Удаляем следующий за ним ответ ассистента, если он есть.
        if len(messages) > _PINNED_MESSAGES and messages[1].get("role") == "assistant":
            messages.pop(1)

        logger.debug("Context overflow: removed oldest history exchange")
