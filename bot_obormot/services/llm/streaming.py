# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Stream generation through the OpenAI-compatible API."""

import json
import logging
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Protocol

import aiohttp

from bot_obormot.common.llm_messages import ChatMessage
from bot_obormot.common.text import log_safe
from bot_obormot.errors import (
    LLMAPIError,
    LLMEmptyResponseError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from bot_obormot.services.llm.constants import FINISH_REASON_LENGTH
from bot_obormot.settings import Settings

_STREAM_DONE = "[DONE]"

logger = logging.getLogger(__name__)


class StreamingClient(Protocol):
    """Minimal client interface for streaming generation."""

    @property
    def settings(self) -> Settings:
        """Return the client settings."""
        ...

    async def get_session(self) -> aiohttp.ClientSession:
        """Return the shared HTTP session."""
        ...

    def normalize_messages(
        self,
        messages: Sequence[object],
    ) -> list[ChatMessage]:
        """Normalize messages for the LLM API."""
        ...


@dataclass
class _StreamState:
    """Tracks what the server produced while the response is streamed."""

    answered: bool = False
    reasoned: bool = False
    finish_reason: str | None = None

    def read(self, chunk: dict[str, Any]) -> str | None:
        """Return the answer text of a chunk and remember how it went."""
        choices = chunk.get("choices", [])

        if not choices:
            return None

        choice = choices[0]
        delta = choice.get("delta", {})

        if choice.get("finish_reason"):
            self.finish_reason = choice["finish_reason"]

        if delta.get("reasoning_content") or delta.get("reasoning"):
            self.reasoned = True

        content = delta.get("content")

        if isinstance(content, str) and content:
            self.answered = True
            return content

        return None

    def check_finished(self) -> None:
        """Report a response that was cut by the max_tokens limit."""
        if self.finish_reason != FINISH_REASON_LENGTH:
            return

        logger.warning(
            "LLM stopped at the max_tokens limit: answer_produced=%s, "
            "reasoning_seen=%s. Consider raising LLM_MAX_TOKENS.",
            self.answered,
            self.reasoned,
        )

        if not self.answered:
            raise LLMEmptyResponseError(self.finish_reason)


@contextmanager
def _translated_transport_errors() -> Iterator[None]:
    """Translate transport failures into the application's LLM errors."""
    try:
        yield
    except TimeoutError as error:
        msg = "LLM generation timed out"
        raise LLMTimeoutError(msg) from error
    except aiohttp.ClientError as error:
        msg = "Could not connect to LLM server"
        raise LLMUnavailableError(msg) from error


def _completion_payload(
    settings: Settings,
    messages: list[ChatMessage],
) -> dict[str, Any]:
    """Build the chat/completions request body for a streamed generation."""
    return {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": settings.LLM_TEMPERATURE,
        "top_p": settings.LLM_TOP_P,
        "max_tokens": settings.LLM_MAX_TOKENS,
        "stream": True,
    }


async def _stream_contents(
    client: StreamingClient,
    url: str,
    payload: dict[str, Any],
) -> AsyncIterator[str]:
    """Post the request and yield the answer text of each server-sent chunk."""
    state = _StreamState()
    session = await client.get_session()

    async with session.post(url, json=payload) as response:
        if response.status != HTTPStatus.OK:
            detail = await response.text()
            logger.error(
                "chat/completions failed: HTTP %s: %s",
                response.status,
                log_safe(detail, 300),
            )
            raise LLMAPIError(response.status, detail)

        async for raw_line in response.content:
            line = raw_line.decode("utf-8").strip()

            if not line or not line.startswith("data:"):
                continue

            data = line[5:].strip()

            if data == _STREAM_DONE:
                break

            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("Invalid LLM stream chunk: %s", data)
                continue

            content = state.read(chunk)

            if content:
                yield content

        state.check_finished()


async def stream_unlimited(
    client: StreamingClient,
    messages: list[ChatMessage],
) -> AsyncIterator[str]:
    """Yield response chunks without semaphore management."""
    settings = client.settings
    url = f"{settings.LLM_BASE_URL.rstrip('/')}/chat/completions"
    payload = _completion_payload(settings, client.normalize_messages(messages))

    with _translated_transport_errors():
        async for content in _stream_contents(client, url, payload):
            yield content
