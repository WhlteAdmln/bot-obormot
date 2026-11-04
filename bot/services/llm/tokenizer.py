"""Интеграция с llama.cpp для подсчёта токенов."""

import asyncio
import logging
from typing import Any, Protocol

import aiohttp

from bot.config import config
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)


class TokenizerClient(Protocol):
    """Минимальный интерфейс LLMClient для токенизации."""

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


async def count_tokens(
    client: TokenizerClient,
    messages: list[dict[str, Any]],
) -> int:
    """Считает токены сообщений через apply-template и tokenize."""

    session = await client._get_session()
    base_url = client._server_url()

    messages = client._normalize_messages(messages)
    prepared_messages = client._prepare_messages_for_count(messages)

    for index, message in enumerate(prepared_messages):
        content = message.get("content")

        if not isinstance(content, (str, list)):
            logger.error(
                "Invalid message content: index=%s, role=%s, type=%s",
                index,
                message.get("role"),
                type(content).__name__,
            )
            raise LLMUnavailableError(f"Invalid message content at index {index}")

    try:
        async with session.post(
            f"{base_url}/apply-template",
            json={
                "model": config.LLM_MODEL,
                "messages": prepared_messages,
                "add_generation_prompt": True,
            },
        ) as response:
            if response.status != 200:
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
            raise LLMUnavailableError("llama.cpp returned an invalid prompt")

        async with session.post(
            f"{base_url}/tokenize",
            json={
                "model": config.LLM_MODEL,
                "content": prompt,
                "add_special": True,
                "parse_special": True,
            },
        ) as response:
            if response.status != 200:
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
            raise LLMUnavailableError("llama.cpp returned an invalid token list")

        return len(tokens)

    except asyncio.TimeoutError as error:
        raise LLMTimeoutError("Timeout while counting prompt tokens") from error

    except aiohttp.ClientError as error:
        raise LLMUnavailableError("Could not count prompt tokens") from error


async def count_text_tokens(client: TokenizerClient, text: str) -> int:
    """Считает токены обычного текста через llama.cpp."""

    if not text:
        return 0

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
            if response.status != 200:
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
            raise LLMUnavailableError("llama.cpp returned an invalid token list")

        return len(tokens)

    except asyncio.TimeoutError as error:
        raise LLMTimeoutError("Timeout while counting text tokens") from error

    except aiohttp.ClientError as error:
        raise LLMUnavailableError("Could not count text tokens") from error
