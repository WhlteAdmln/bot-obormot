# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fit message history into the available LLM context window."""

import logging
import math
from collections.abc import Mapping, Sequence
from typing import Protocol

from bot_obormot.common.llm_messages import ChatMessage
from bot_obormot.errors import InputTooLongError, LLMUnavailableError
from bot_obormot.services.llm.constants import (
    CONTEXT_SAFETY_MARGIN,
    COUNTING_MODE_ESTIMATE,
    ESTIMATE_CONTEXT_SAFETY_FACTOR,
    IMAGE_TOKEN_RESERVE,
    ROLE_ASSISTANT,
    ROLE_USER,
)
from bot_obormot.settings import Settings

logger = logging.getLogger(__name__)

# The system prompt and the current user message are always kept.
_PINNED_MESSAGES = 2


class FittingClient(Protocol):
    """Minimal client interface required for fitting message history."""

    @property
    def settings(self) -> Settings:
        """Return the client settings."""
        ...

    async def get_context_size(self) -> int:
        """Returns the context window size of the model."""

    def normalize_messages(
        self,
        messages: Sequence[object],
    ) -> list[ChatMessage]:
        """Normalize messages for the LLM API."""
        ...

    @staticmethod
    def count_images(messages: Sequence[Mapping[str, object]]) -> int:
        """Count image parts in normalized messages."""
        ...

    async def count_tokens(self, messages: list[ChatMessage]) -> int:
        """Counts the prompt tokens of the messages."""

    async def get_token_counting_mode(self) -> str:
        """Returns the selected token counting mode."""


async def fit_messages_to_context(
    client: FittingClient,
    system_prompt: str,
    history: list[ChatMessage],
    user_message: object,
) -> list[ChatMessage]:
    """Fit the largest possible history into the model context."""
    context_size = await client.get_context_size()
    counting_mode = await client.get_token_counting_mode()
    safety_margin = CONTEXT_SAFETY_MARGIN
    if counting_mode == COUNTING_MODE_ESTIMATE:
        safety_margin += math.ceil(context_size * ESTIMATE_CONTEXT_SAFETY_FACTOR)

    history = list(history)

    # History must start with a user message.
    while history and history[0].get("role") != ROLE_USER:
        history.pop(0)

    messages = client.normalize_messages(
        [
            {"role": "system", "content": system_prompt},
            *history,
            {"role": "user", "content": user_message},
        ]
    )

    while True:
        # The number of images changes when older exchanges are removed.
        image_count = client.count_images(messages)

        image_reserved_tokens = IMAGE_TOKEN_RESERVE * image_count
        reserved_tokens = (
            client.settings.LLM_MAX_TOKENS + safety_margin + image_reserved_tokens
        )

        available_tokens = context_size - reserved_tokens

        if available_tokens <= 0:
            msg = "Not enough context space for the request."
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
                client.settings.LLM_MAX_TOKENS,
                safety_margin,
                image_count,
                image_reserved_tokens,
                len(messages) - _PINNED_MESSAGES,
            )
            return messages

        # Only the system prompt and current user message remain;
        # even these do not fit into the available context.
        if len(messages) <= _PINNED_MESSAGES:
            msg = "Message is too large for the model context."
            raise InputTooLongError(msg)

        # History must be organized in user/assistant pairs.
        if messages[1].get("role") != ROLE_USER:
            msg = "Invalid history: expected a user message"
            raise LLMUnavailableError(msg)

        # Remove the oldest user message.
        messages.pop(1)

        # Remove the following assistant response, if present.
        if (
            len(messages) > _PINNED_MESSAGES
            and messages[1].get("role") == ROLE_ASSISTANT
        ):
            messages.pop(1)

        logger.debug("Context overflow: removed oldest history exchange")
