"""Потоковая генерация через OpenAI-compatible API."""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any, Protocol

import aiohttp

from bot.config import config
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)


class StreamingClient(Protocol):
    """Минимальный интерфейс клиента для потоковой генерации."""

    async def _get_session(self) -> aiohttp.ClientSession: ...

    def _normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...


async def stream_unlimited(
    client: StreamingClient,
    messages: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Получает потоковые фрагменты ответа без управления semaphore."""

    url = f"{config.LLM_BASE_URL.rstrip('/')}/chat/completions"
    normalized_messages = client._normalize_messages(messages)

    payload = {
        "model": config.LLM_MODEL,
        "messages": normalized_messages,
        "temperature": config.LLM_TEMPERATURE,
        "top_p": config.LLM_TOP_P,
        "max_tokens": config.LLM_MAX_TOKENS,
        "stream": True,
    }

    try:
        session = await client._get_session()

        async with session.post(url, json=payload) as response:
            if response.status != 200:
                detail = await response.text()
                logger.error(
                    "chat/completions failed: HTTP %s: %s",
                    response.status,
                    log_safe(detail, 300),
                )
                raise LLMAPIError(response.status, detail)

            async for line in response.content:
                line = line.decode("utf-8").strip()

                if not line or not line.startswith("data:"):
                    continue

                data = line[5:].strip()

                if data == "[DONE]":
                    break

                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("Invalid LLM stream chunk: %s", data)
                    continue

                choices = chunk.get("choices", [])

                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content = delta.get("content")

                if isinstance(content, str) and content:
                    yield content

    except TimeoutError as error:
        raise LLMTimeoutError("LLM generation timed out") from error

    except aiohttp.ClientError as error:
        raise LLMUnavailableError("Could not connect to LLM server") from error
