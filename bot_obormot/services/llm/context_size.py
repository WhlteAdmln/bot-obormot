# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Retrieve and cache the model context window size."""

import logging
from http import HTTPStatus
from typing import Any, Protocol

import aiohttp

from bot_obormot.common.text import log_safe
from bot_obormot.errors import LLMUnavailableError
from bot_obormot.settings import Settings

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
    """Minimal client interface for determining the context size."""

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
    """Extract known context fields from the server response."""
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


def _models_payload_context(data: dict[str, Any], model_name: str) -> int | None:
    models = data.get("data") or data.get("models")
    if not isinstance(models, list) or not models:
        return None

    model = next(
        (
            item
            for item in models
            if isinstance(item, dict) and item.get("id") == model_name
        ),
        None,
    )
    if model is None and len(models) == 1 and isinstance(models[0], dict):
        model = models[0]
    return _extract_context_size(model) if isinstance(model, dict) else None


async def _context_size_from_props(
    client: ContextSizeClient,
    session: aiohttp.ClientSession,
) -> int | None:
    """Read the context size from the llama.cpp /props endpoint, if available."""
    settings = client.settings
    async with session.get(
        f"{client.get_server_url()}/props",
        params={"model": settings.LLM_MODEL},
        timeout=aiohttp.ClientTimeout(total=min(5, settings.LLM_TIMEOUT)),
    ) as response:
        if response.status != HTTPStatus.OK:
            detail = await response.text()
            logger.debug(
                "Optional /props endpoint unavailable: HTTP %s: %s",
                response.status,
                log_safe(detail, 200),
            )
            return None
        data = await _read_json(response)
        context_size = _extract_context_size(data or {})
        if context_size is not None:
            logger.info(
                "LLM context size detected via /props: %s",
                context_size,
            )
        return context_size


async def _context_size_from_models(
    settings: Settings,
    session: aiohttp.ClientSession,
) -> int | None:
    """Read ``max_model_len`` and similar fields from the /models model card."""
    async with session.get(
        f"{settings.LLM_BASE_URL}/models",
        timeout=aiohttp.ClientTimeout(total=min(5, settings.LLM_TIMEOUT)),
    ) as response:
        if response.status != HTTPStatus.OK:
            logger.debug(
                "Could not detect context via /models: HTTP %s",
                response.status,
            )
            return None
        data = await _read_json(response)
        context_size = _models_payload_context(data or {}, settings.LLM_MODEL)
        if context_size is not None:
            logger.info(
                "LLM context size detected via /models: %s",
                context_size,
            )
        return context_size


async def get_context_size(client: ContextSizeClient) -> int:
    """Return the context size from settings, llama.cpp /props, or OpenAI /models."""
    settings = client.settings
    configured_size = settings.LLM_CONTEXT_SIZE
    if configured_size is not None:
        logger.info("LLM context size configured: %s tokens", configured_size)
        return configured_size

    session = await client.get_session()

    # /props is an optional llama.cpp extension, not a required part of the API.
    try:
        context_size = await _context_size_from_props(client, session)
    except (TimeoutError, aiohttp.ClientError) as error:
        logger.debug("Optional /props endpoint unavailable: %s", type(error).__name__)
    else:
        if context_size is not None:
            return context_size

    # Some servers, such as certain vLLM builds, add max_model_len
    # to the model card. This field is not standardized by the OpenAI API,
    # so this lookup is best effort.
    try:
        context_size = await _context_size_from_models(settings, session)
    except (TimeoutError, aiohttp.ClientError) as error:
        logger.debug(
            "Could not query /models for context size: %s",
            type(error).__name__,
        )
    else:
        if context_size is not None:
            return context_size

    msg = "Could not determine the context size. Set LLM_CONTEXT_SIZE in .env"
    raise LLMUnavailableError(msg)
