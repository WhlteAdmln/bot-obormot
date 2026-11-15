# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""HTTP client for an OpenAI-compatible LLM server."""

import asyncio
import logging
from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any

import aiohttp

from bot.config import config
from bot.services.llm.context_size import get_context_size as fetch_context_size
from bot.services.llm.endpoints import server_url
from bot.services.llm.fitting import fit_messages_to_context
from bot.services.llm.messages import (
    count_images as count_message_images,
)
from bot.services.llm.messages import (
    normalize_content,
    normalize_messages,
)
from bot.services.llm.messages import (
    prepare_messages_for_count as prepare_for_token_counting,
)
from bot.services.llm.session import get_session
from bot.services.llm.streaming import stream_unlimited
from bot.services.llm.tokenizer import (
    count_text_tokens as tokenize_text,
)
from bot.services.llm.tokenizer import (
    count_tokens as tokenize_messages,
)
from bot.services.llm.tokenizer import (
    get_token_counting_mode as resolve_token_counting_mode,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """Client that keeps one HTTP session and limits concurrent generations."""

    def __init__(self) -> None:
        """Creates the client without opening a session."""
        self.session: aiohttp.ClientSession | None = None
        self.semaphore = asyncio.Semaphore(config.LLM_MAX_CONCURRENT_GENERATIONS)
        self._context_size: int | None = None
        self._token_counting_mode: str | None = None
        self._token_counting_lock = asyncio.Lock()

    async def start(self) -> None:
        """Инициализирует HTTP-сессию."""
        await self._get_session()
        logger.info("LLM client initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        return await get_session(self)

    async def get_session(self) -> aiohttp.ClientSession:
        """Return the shared HTTP session."""
        return await self._get_session()

    def _server_url(self) -> str:
        return server_url()

    def get_server_url(self) -> str:
        """Return the configured LLM server URL."""
        return self._server_url()

    @staticmethod
    def _normalize_content(content: object) -> str | list[Any]:
        return normalize_content(content)

    def _normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return normalize_messages(messages)

    def normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Normalize messages for the LLM API."""
        return self._normalize_messages(messages)

    async def get_context_size(self) -> int:
        """Получает размер контекста активной модели."""
        context_size = self._context_size
        if context_size is None:
            context_size = await fetch_context_size(self)
            self._context_size = context_size
        return context_size

    @staticmethod
    def _prepare_messages_for_count(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return prepare_for_token_counting(messages)

    @staticmethod
    def _count_images(messages: list[dict[str, Any]]) -> int:
        return count_message_images(messages)

    @staticmethod
    def prepare_messages_for_count(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Prepare messages for server-side token counting."""
        return prepare_for_token_counting(messages)

    @staticmethod
    def count_images(messages: list[dict[str, Any]]) -> int:
        """Count image parts in normalized messages."""
        return count_message_images(messages)

    async def get_token_counting_mode(self) -> str:
        """Возвращает выбранный режим подсчёта токенов."""
        configured_mode = config.LLM_TOKEN_COUNTING
        if configured_mode != "auto":
            return configured_mode

        mode = self._token_counting_mode
        if mode is not None:
            return mode

        async with self._token_counting_lock:
            mode = self._token_counting_mode
            if mode is None:
                mode = await resolve_token_counting_mode(self)
                self._token_counting_mode = mode
        return mode

    async def count_tokens(
        self,
        messages: list[dict[str, Any]],
    ) -> int:
        """Считает токены через llama.cpp или консервативную оценку."""
        return await tokenize_messages(self, messages)

    async def count_text_tokens(self, text: str) -> int:
        """Считает количество токенов обычного текста."""
        return await tokenize_text(self, text)

    async def fit_messages_to_context(
        self,
        system_prompt: str,
        history: list[dict[str, Any]],
        user_message: object,
    ) -> list[dict[str, Any]]:
        """Подбирает максимально возможную историю под контекст модели."""
        return await fit_messages_to_context(
            self,
            system_prompt,
            history,
            user_message,
        )

    async def stream(
        self,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[str]:
        """Streams the reply tokens while holding a generation slot."""
        async with self.semaphore:
            async for token in self._stream_unlimited(messages):
                yield token

    async def _stream_unlimited(
        self,
        messages: list[dict[str, Any]],
    ) -> AsyncIterator[str]:
        """Делегирует потоковую генерацию отдельному модулю."""
        async for chunk in stream_unlimited(self, messages):
            yield chunk

    async def health_check(self) -> tuple[bool, str]:
        """Проверяет LLM-сервер через /health или стандартный /models."""
        try:
            session = await self._get_session()

            try:
                async with session.get(
                    f"{self._server_url()}/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as response:
                    if response.status == HTTPStatus.OK:
                        try:
                            data = await response.json()
                        except (aiohttp.ClientError, ValueError, TypeError):
                            data = None
                        if isinstance(data, dict) and data.get("status") == "ok":
                            return True, "Доступен"
            except (TimeoutError, aiohttp.ClientError):
                logger.debug("Optional LLM /health endpoint unavailable", exc_info=True)

            # /v1/models — стандартный OpenAI endpoint; HTTP 200 означает,
            # что API доступен, даже если сервер не реализует /health.
            async with session.get(
                f"{config.LLM_BASE_URL}/models",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status == HTTPStatus.OK:
                    return True, "Доступен"
                return False, f"HTTP {response.status}: LLM API недоступен"

        except TimeoutError:
            return False, "Тайм-аут при обращении к LLM-серверу"

        except aiohttp.ClientError:
            return False, "LLM-сервер недоступен"

        except Exception:
            logger.exception("LLM health check failed")
            return False, "Ошибка проверки LLM-сервера"

    async def close(self) -> None:
        """Закрывает HTTP-сессию."""
        if self.session and not self.session.closed:
            await self.session.close()

        self.session = None


llm_client = LLMClient()
