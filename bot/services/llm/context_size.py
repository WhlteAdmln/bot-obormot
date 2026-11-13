# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Получение и кеширование размера контекстного окна модели."""

import logging
from http import HTTPStatus
from typing import Any, Protocol

import aiohttp

from bot.config import config
from bot.errors import LLMUnavailableError
from bot.utils.text import log_safe

logger = logging.getLogger(__name__)

_CONTEXT_FIELDS = (
    "max_model_len",
    "context_length",
    "max_context_length",
    "model_max_length",
    "max_position_embeddings",
    "n_ctx",
)


class ContextSizeClient(Protocol):
    """Минимальный интерфейс клиента для определения размера контекста."""

    _context_size: int | None

    async def _get_session(self) -> aiohttp.ClientSession: ...

    def _server_url(self) -> str: ...


async def _read_json(response: aiohttp.ClientResponse) -> dict[str, Any] | None:
    try:
        data = await response.json()
    except (aiohttp.ClientError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _extract_context_size(data: dict[str, Any]) -> int | None:
    """Извлекает известные поля контекста из ответа сервера."""
    for field in _CONTEXT_FIELDS:
        value = _positive_int(data.get(field))
        if value is not None:
            return value

    for nested_name in ("default_generation_settings", "metadata", "meta", "config"):
        nested = data.get(nested_name)
        if isinstance(nested, dict):
            value = _extract_context_size(nested)
            if value is not None:
                return value

    return None


def _models_payload_context(data: dict[str, Any]) -> int | None:
    models = data.get("data") or data.get("models")
    if not isinstance(models, list) or not models:
        return None

    model = next(
        (
            item
            for item in models
            if isinstance(item, dict) and item.get("id") == config.LLM_MODEL
        ),
        None,
    )
    if model is None and len(models) == 1 and isinstance(models[0], dict):
        model = models[0]
    return _extract_context_size(model) if isinstance(model, dict) else None


async def get_context_size(client: ContextSizeClient) -> int:
    """Возвращает контекст: настройка, llama.cpp /props, затем OpenAI /models."""
    if client._context_size is not None:
        return client._context_size

    configured_size = config.LLM_CONTEXT_SIZE
    if configured_size is not None:
        client._context_size = configured_size
        logger.info("LLM context size configured: %s tokens", configured_size)
        return configured_size

    session = await client._get_session()

    # /props — необязательное расширение llama.cpp, а не обязательная часть API.
    try:
        async with session.get(
            f"{client._server_url()}/props",
            params={"model": config.LLM_MODEL},
            timeout=aiohttp.ClientTimeout(total=min(5, config.LLM_TIMEOUT)),
        ) as response:
            if response.status == HTTPStatus.OK:
                data = await _read_json(response)
                context_size = _extract_context_size(data or {})
                if context_size is not None:
                    client._context_size = context_size
                    logger.info(
                        "LLM context size detected via /props: %s",
                        context_size,
                    )
                    return context_size
            else:
                detail = await response.text()
                logger.debug(
                    "Optional /props endpoint unavailable: HTTP %s: %s",
                    response.status,
                    log_safe(detail, 200),
                )
    except (TimeoutError, aiohttp.ClientError) as error:
        logger.debug("Optional /props endpoint unavailable: %s", type(error).__name__)

    # Некоторые серверы (например, отдельные сборки vLLM) добавляют max_model_len
    # в карточку модели. Поле не стандартизировано OpenAI API, поэтому это best effort.
    try:
        async with session.get(
            f"{config.LLM_BASE_URL}/models",
            timeout=aiohttp.ClientTimeout(total=min(5, config.LLM_TIMEOUT)),
        ) as response:
            if response.status == HTTPStatus.OK:
                data = await _read_json(response)
                context_size = _models_payload_context(data or {})
                if context_size is not None:
                    client._context_size = context_size
                    logger.info(
                        "LLM context size detected via /models: %s",
                        context_size,
                    )
                    return context_size
            else:
                logger.debug(
                    "Could not detect context via /models: HTTP %s",
                    response.status,
                )
    except (TimeoutError, aiohttp.ClientError) as error:
        logger.debug(
            "Could not query /models for context size: %s",
            type(error).__name__,
        )

    msg = "Не удалось определить размер контекста. Задайте LLM_CONTEXT_SIZE в .env"
    raise LLMUnavailableError(msg)
