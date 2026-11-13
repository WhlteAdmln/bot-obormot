# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Подсчёт токенов: llama.cpp или консервативная оценка."""

import asyncio
import logging
import math
from http import HTTPStatus
from typing import Any, Protocol

import aiohttp

from bot.config import config
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)
_ESTIMATE_CHARS_PER_TOKEN = 3
_ESTIMATE_MESSAGE_OVERHEAD = 8
_PROBE_TEXT = "tokenizer availability check"
_MODE_LLAMACPP = "llamacpp"
_MODE_ESTIMATE = "estimate"


class TokenizerClient(Protocol):
    """Минимальный интерфейс LLMClient для токенизации."""

    _token_counting_mode: str | None
    _token_counting_lock: asyncio.Lock

    async def _get_session(self) -> aiohttp.ClientSession: ...

    def _server_url(self) -> str: ...

    def _normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    @staticmethod
    def _prepare_messages_for_count(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


async def get_token_counting_mode(client: TokenizerClient) -> str:
    """Выбирает backend токенизации один раз на экземпляр клиента."""
    configured_mode = config.LLM_TOKEN_COUNTING
    if configured_mode != "auto":
        return configured_mode

    cached_mode = client._token_counting_mode
    if cached_mode is not None:
        return cached_mode

    async with client._token_counting_lock:
        if client._token_counting_mode is not None:
            return client._token_counting_mode

        try:
            session = await client._get_session()
            async with session.post(
                f"{client._server_url()}/tokenize",
                json={
                    "model": config.LLM_MODEL,
                    "content": _PROBE_TEXT,
                    "add_special": False,
                    "parse_special": True,
                },
                timeout=aiohttp.ClientTimeout(total=min(5, config.LLM_TIMEOUT)),
            ) as response:
                data = (
                    await response.json() if response.status == HTTPStatus.OK else None
                )
                if isinstance(data, dict) and isinstance(data.get("tokens"), list):
                    client._token_counting_mode = _MODE_LLAMACPP
                else:
                    client._token_counting_mode = _MODE_ESTIMATE
        except (TimeoutError, aiohttp.ClientError, ValueError, TypeError):
            client._token_counting_mode = _MODE_ESTIMATE

        if client._token_counting_mode == _MODE_ESTIMATE:
            logger.warning(
                "LLM server does not expose the llama.cpp tokenizer; "
                "using approximate token counting"
            )
        else:
            logger.info("Using llama.cpp tokenizer")

        return client._token_counting_mode


def _text_from_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for part in content:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text":
            value = part.get("text")
            if isinstance(value, str):
                parts.append(value)
    return "".join(parts)


def estimate_text_tokens(text: str) -> int:
    """Консервативно оценивает токены текста без обращения к серверу."""
    if not text:
        return 0
    return math.ceil(len(text) / _ESTIMATE_CHARS_PER_TOKEN)


def estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    """Оценивает текстовые токены сообщений и служебные затраты на сообщение."""
    return sum(
        estimate_text_tokens(_text_from_content(message.get("content")))
        + _ESTIMATE_MESSAGE_OVERHEAD
        for message in messages
    )


async def _count_tokens_llamacpp(
    client: TokenizerClient,
    messages: list[dict[str, Any]],
) -> int:
    session = await client._get_session()
    base_url = client._server_url()
    normalized_messages = client._normalize_messages(messages)
    prepared_messages = client._prepare_messages_for_count(normalized_messages)

    for index, message in enumerate(prepared_messages):
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

    async with session.post(
        f"{base_url}/apply-template",
        json={
            "model": config.LLM_MODEL,
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
            "model": config.LLM_MODEL,
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
    """Считает токены сообщений выбранным backend-ом."""
    mode = await get_token_counting_mode(client)
    if mode == "estimate":
        normalized_messages = client._normalize_messages(messages)
        return estimate_message_tokens(normalized_messages)

    try:
        return await _count_tokens_llamacpp(client, messages)
    except TimeoutError as error:
        msg = "Timeout while counting prompt tokens"
        raise LLMTimeoutError(msg) from error
    except aiohttp.ClientError as error:
        msg = "Could not count prompt tokens"
        raise LLMUnavailableError(msg) from error


async def count_text_tokens(client: TokenizerClient, text: str) -> int:
    """Считает токены обычного текста."""
    if not text:
        return 0

    mode = await get_token_counting_mode(client)
    if mode == "estimate":
        return estimate_text_tokens(text)

    try:
        session = await client._get_session()
        async with session.post(
            f"{client._server_url()}/tokenize",
            json={
                "model": config.LLM_MODEL,
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
    except TimeoutError as error:
        msg = "Timeout while counting text tokens"
        raise LLMTimeoutError(msg) from error
    except aiohttp.ClientError as error:
        msg = "Could not count text tokens"
        raise LLMUnavailableError(msg) from error
