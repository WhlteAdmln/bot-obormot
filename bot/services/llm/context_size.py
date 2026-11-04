"""Получение и кеширование размера контекстного окна модели."""

import asyncio
import logging
from typing import Protocol

import aiohttp

from bot.config import config
from bot.errors import LLMAPIError, LLMTimeoutError, LLMUnavailableError
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)


class ContextSizeClient(Protocol):
    """Минимальный интерфейс клиента, необходимый для запроса /props."""

    _context_size: int | None

    async def _get_session(self) -> aiohttp.ClientSession: ...

    def _server_url(self) -> str: ...


async def get_context_size(client: ContextSizeClient) -> int:
    """Возвращает размер контекста, при необходимости запрашивая llama.cpp."""

    if client._context_size is not None:
        return client._context_size

    url = f"{client._server_url()}/props"

    try:
        session = await client._get_session()

        async with session.get(
            url,
            params={"model": config.LLM_MODEL},
        ) as response:
            if response.status != 200:
                detail = await response.text()
                logger.error(
                    "props failed: HTTP %s: %s",
                    response.status,
                    log_safe(detail, 300),
                )
                raise LLMAPIError(response.status, detail)

            data = await response.json()

        context_size = data.get("n_ctx")

        if context_size is None:
            settings = data.get("default_generation_settings") or {}
            context_size = settings.get("n_ctx")

        if (
            not isinstance(context_size, int)
            or isinstance(context_size, bool)
            or context_size <= 0
        ):
            logger.error(
                "Invalid context response: model=%s, response=%r",
                config.LLM_MODEL,
                data,
            )
            raise LLMUnavailableError("llama.cpp returned an invalid n_ctx value")

        client._context_size = context_size

        logger.info(
            "LLM context size detected: %s tokens (model: %s)",
            context_size,
            config.LLM_MODEL,
        )

        return context_size

    except asyncio.TimeoutError as error:
        raise LLMTimeoutError("Timeout while requesting context size") from error

    except aiohttp.ClientError as error:
        raise LLMUnavailableError("Could not connect to llama.cpp") from error
