import asyncio
import logging
from typing import Any, AsyncIterator

import aiohttp

from bot.config import config
from bot.services.llm.fitting import fit_messages_to_context
from bot.services.llm.context_size import get_context_size as fetch_context_size
from bot.services.llm.endpoints import server_url
from bot.services.llm.messages import (
    count_images,
    normalize_content,
    normalize_messages,
    prepare_messages_for_count,
)
from bot.services.llm.session import get_session
from bot.services.llm.streaming import stream_unlimited
from bot.services.llm.tokenizer import (
    count_text_tokens as tokenize_text,
    count_tokens as tokenize_messages,
)

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None
        self.semaphore = asyncio.Semaphore(config.LLM_MAX_CONCURRENT_GENERATIONS)
        self._context_size: int | None = None

    async def start(self) -> None:
        """Инициализирует HTTP-сессию."""
        await self._get_session()
        logger.info("LLM client initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        return await get_session(self)

    def _server_url(self) -> str:
        return server_url()

    @staticmethod
    def _normalize_content(content: Any) -> str | list:
        return normalize_content(content)

    def _normalize_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return normalize_messages(messages)

    async def get_context_size(self) -> int:
        """Получает размер контекста активной модели."""

        return await fetch_context_size(self)

    @staticmethod
    def _prepare_messages_for_count(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return prepare_messages_for_count(messages)

    @staticmethod
    def _count_images(messages: list[dict[str, Any]]) -> int:
        return count_images(messages)

    async def count_tokens(
        self,
        messages: list[dict[str, Any]],
    ) -> int:
        """Считает токены через apply-template и tokenize."""

        return await tokenize_messages(self, messages)

    async def count_text_tokens(self, text: str) -> int:
        """Считает количество токенов обычного текста через llama.cpp."""

        return await tokenize_text(self, text)

    async def fit_messages_to_context(
        self,
        system_prompt: str,
        history: list[dict[str, Any]],
        user_message: Any,
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
        """Проверяет доступность llama.cpp."""

        try:
            session = await self._get_session()

            async with session.get(
                f"{self._server_url()}/health",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as response:
                if response.status != 200:
                    detail = await response.text()
                    return False, f"HTTP {response.status}: {detail[:150]}"

                data = await response.json()

                if data.get("status") == "ok":
                    return True, "Доступен"

                return False, "Неожиданный ответ сервера"

        except asyncio.TimeoutError:
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
