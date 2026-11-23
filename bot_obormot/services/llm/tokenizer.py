# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Token counting: llama.cpp or a conservative estimate."""

import logging
import math
from http import HTTPStatus
from typing import Any, Protocol

import aiohttp

from bot_obormot.common.text import log_safe
from bot_obormot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot_obormot.services.llm.constants import COUNTING_MODE_ESTIMATE, PART_TYPE_TEXT
from bot_obormot.settings import Settings

logger = logging.getLogger(__name__)
_ESTIMATE_CHARS_PER_TOKEN = 3
_ESTIMATE_MESSAGE_OVERHEAD = 8
_PROBE_TEXT = "tokenizer availability check"
_MODE_LLAMACPP = "llamacpp"


class TokenizerClient(Protocol):
    """Minimal client interface for tokenization."""

    @property
    def settings(self) -> Settings:
        """Return the client settings."""
        ...

    async def get_session(self) -> aiohttp.ClientSession:
        """Return the shared HTTP session."""
        ...

    def get_server_url(self) -> str:
        """Return the configured LLM server URL."""
        ...

    def normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Normalize messages for the LLM API."""
        ...

    @staticmethod
    def prepare_messages_for_count(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Prepare messages for server-side token counting."""
        ...

    async def get_token_counting_mode(self) -> str:
        """Return the selected token counting backend."""
        ...


async def _probe_tokenizer(client: TokenizerClient) -> str:
    """Ask the server to tokenize a probe text and return the resulting mode."""
    session = await client.get_session()
    async with session.post(
        f"{client.get_server_url()}/tokenize",
        json={
            "model": client.settings.LLM_MODEL,
            "content": _PROBE_TEXT,
            "add_special": False,
            "parse_special": True,
        },
        timeout=aiohttp.ClientTimeout(total=min(5, client.settings.LLM_TIMEOUT)),
    ) as response:
        data = await response.json() if response.status == HTTPStatus.OK else None
        return (
            _MODE_LLAMACPP
            if isinstance(data, dict) and isinstance(data.get("tokens"), list)
            else COUNTING_MODE_ESTIMATE
        )


async def get_token_counting_mode(client: TokenizerClient) -> str:
    """Detects the available token counting backend."""
    try:
        mode = await _probe_tokenizer(client)
    except (TimeoutError, aiohttp.ClientError, ValueError, TypeError):
        mode = COUNTING_MODE_ESTIMATE

    if mode == COUNTING_MODE_ESTIMATE:
        logger.warning(
            "LLM server does not expose the llama.cpp tokenizer; "
            "using approximate token counting"
        )
    else:
        logger.info("Using llama.cpp tokenizer")

    return mode


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == PART_TYPE_TEXT:
            value = part.get("text")
            if isinstance(value, str):
                parts.append(value)
    return "".join(parts)


def estimate_text_tokens(text: str) -> int:
    """Estimate text tokens conservatively without querying the server."""
    if not text:
        return 0
    return math.ceil(len(text) / _ESTIMATE_CHARS_PER_TOKEN)


def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate message text tokens and per-message overhead."""
    return sum(
        estimate_text_tokens(_text_from_content(message.get("content")))
        + _ESTIMATE_MESSAGE_OVERHEAD
        for message in messages
    )


def _check_message_contents(messages: list[dict[str, Any]]) -> None:
    """Reject messages whose content is neither text nor a list of parts."""
    for index, message in enumerate(messages):
        content = message.get("content")
        if not isinstance(content, (str, list)):
            logger.error(
                "Invalid message content: index=%s, role=%s, type=%s",
                index,
                message.get("role"),
                type(content).__name__,
            )
            msg = f"Invalid message content at index {index}"
            raise LLMUnavailableError(msg)


async def _count_tokens_llamacpp(
    client: TokenizerClient,
    messages: list[dict[str, Any]],
) -> int:
    session = await client.get_session()
    base_url = client.get_server_url()
    normalized_messages = client.normalize_messages(messages)
    prepared_messages = client.prepare_messages_for_count(normalized_messages)
    _check_message_contents(prepared_messages)

    async with session.post(
        f"{base_url}/apply-template",
        json={
            "model": client.settings.LLM_MODEL,
            "messages": prepared_messages,
            "add_generation_prompt": True,
        },
    ) as response:
        if response.status != HTTPStatus.OK:
            detail = await response.text()
            logger.error(
                "apply-template failed: HTTP %s: %s",
                response.status,
                log_safe(detail, 300),
            )
            raise LLMAPIError(response.status, detail)
        template_data = await response.json()

    prompt = template_data.get("prompt")
    if not isinstance(prompt, str):
        msg = "LLM server returned an invalid tokenization prompt"
        raise LLMUnavailableError(msg)

    async with session.post(
        f"{base_url}/tokenize",
        json={
            "model": client.settings.LLM_MODEL,
            "content": prompt,
            "add_special": True,
            "parse_special": True,
        },
    ) as response:
        if response.status != HTTPStatus.OK:
            detail = await response.text()
            logger.error(
                "tokenize failed: HTTP %s: %s",
                response.status,
                log_safe(detail, 300),
            )
            raise LLMAPIError(response.status, detail)
        token_data = await response.json()

    tokens = token_data.get("tokens")
    if not isinstance(tokens, list):
        msg = "LLM server returned an invalid token list"
        raise LLMUnavailableError(msg)
    return len(tokens)


async def count_tokens(
    client: TokenizerClient,
    messages: list[dict[str, Any]],
) -> int:
    """Count message tokens using the selected backend."""
    mode = await client.get_token_counting_mode()
    if mode == COUNTING_MODE_ESTIMATE:
        normalized_messages = client.normalize_messages(messages)
        return estimate_message_tokens(normalized_messages)

    try:
        return await _count_tokens_llamacpp(client, messages)
    except TimeoutError as error:
        msg = "Timeout while counting prompt tokens"
        raise LLMTimeoutError(msg) from error
    except aiohttp.ClientError as error:
        msg = "Could not count prompt tokens"
        raise LLMUnavailableError(msg) from error


async def _tokenize_text(client: TokenizerClient, text: str) -> int:
    """Count the tokens of a plain text with the server's /tokenize endpoint."""
    session = await client.get_session()
    async with session.post(
        f"{client.get_server_url()}/tokenize",
        json={
            "model": client.settings.LLM_MODEL,
            "content": text,
            "add_special": False,
            "parse_special": True,
        },
    ) as response:
        if response.status != HTTPStatus.OK:
            detail = await response.text()
            logger.error(
                "Text tokenize failed: HTTP %s: %s",
                response.status,
                log_safe(detail, 300),
            )
            raise LLMAPIError(response.status, detail)
        token_data = await response.json()

    tokens = token_data.get("tokens")
    if not isinstance(tokens, list):
        msg = "LLM server returned an invalid token list"
        raise LLMUnavailableError(msg)
    return len(tokens)


async def count_text_tokens(client: TokenizerClient, text: str) -> int:
    """Count tokens in plain text."""
    if not text:
        return 0

    mode = await client.get_token_counting_mode()
    if mode == COUNTING_MODE_ESTIMATE:
        return estimate_text_tokens(text)

    try:
        return await _tokenize_text(client, text)
    except TimeoutError as error:
        msg = "Timeout while counting text tokens"
        raise LLMTimeoutError(msg) from error
    except aiohttp.ClientError as error:
        msg = "Could not count text tokens"
        raise LLMUnavailableError(msg) from error
