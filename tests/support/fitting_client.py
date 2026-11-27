# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Fake fitting client that counts tokens from the message text."""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from bot_obormot.common.llm_messages import ChatMessage
from bot_obormot.settings import Settings

IMAGE_PART_TYPE = "image_url"
MESSAGE_OVERHEAD_TOKENS = 4


def _parts(message: Mapping[str, object]) -> list[object]:
    content = message.get("content")
    return list(content) if isinstance(content, list) else [content]


def _is_image(part: object) -> bool:
    return isinstance(part, dict) and part.get("type") == IMAGE_PART_TYPE


def _text_length(part: object) -> int:
    if isinstance(part, dict):
        return len(str(part.get("text", "")))
    return len(str(part))


class MeasuringFittingClient:
    """Fitting client whose token count is a fixed function of the messages.

    A message costs a fixed overhead plus one token per character of its text;
    image parts cost nothing here, since the fitting reserves them separately.
    """

    def __init__(
        self,
        context_size: int,
        *,
        max_tokens: int,
        counting_mode: str,
    ) -> None:
        """Initializes the test double."""
        changes = {"LLM_MAX_TOKENS": max_tokens}
        self.settings = replace(Settings(), **changes)
        self.context_size = context_size
        self.counting_mode = counting_mode

    async def get_context_size(self) -> int:
        """Returns the configured context size."""
        return self.context_size

    async def get_token_counting_mode(self) -> str:
        """Returns the configured counting mode."""
        return self.counting_mode

    @staticmethod
    def normalize_messages(messages: Sequence[object]) -> list[ChatMessage]:
        """Returns the messages unchanged."""
        return [message for message in messages if isinstance(message, dict)]

    @staticmethod
    def count_images(messages: Sequence[Mapping[str, object]]) -> int:
        """Counts the image parts of the messages."""
        return sum(
            1 for message in messages for part in _parts(message) if _is_image(part)
        )

    @staticmethod
    async def count_tokens(messages: Sequence[Mapping[str, object]]) -> int:
        """Counts the tokens of the messages from their text length."""
        return sum(
            MESSAGE_OVERHEAD_TOKENS
            + sum(_text_length(part) for part in _parts(message))
            for message in messages
        )
