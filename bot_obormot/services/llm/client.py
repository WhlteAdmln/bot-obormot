# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""HTTP client for an OpenAI-compatible LLM server."""

import asyncio
import logging
from collections.abc import AsyncIterator
from http import HTTPStatus
from typing import Any

import aiohttp

from bot_obormot.services.llm import texts
from bot_obormot.services.llm.constants import COUNTING_MODE_AUTO
from bot_obormot.services.llm.context_size import get_context_size as fetch_context_size
from bot_obormot.services.llm.endpoints import server_url
from bot_obormot.services.llm.fitting import fit_messages_to_context
from bot_obormot.services.llm.messages import (
    count_images as count_message_images,
)
from bot_obormot.services.llm.messages import normalize_messages
from bot_obormot.services.llm.messages import (
    prepare_messages_for_count as prepare_for_token_counting,
)
from bot_obormot.services.llm.session import get_session
from bot_obormot.services.llm.streaming import stream_unlimited
from bot_obormot.services.llm.tokenizer import (
    count_text_tokens as tokenize_text,
)
from bot_obormot.services.llm.tokenizer import (
    count_tokens as tokenize_messages,
)
from bot_obormot.services.llm.tokenizer import (
    get_token_counting_mode as resolve_token_counting_mode,
)
from bot_obormot.settings import Settings, get_settings

_HEALTH_OK_STATUS = "ok"

logger = logging.getLogger(__name__)


async def _json_or_none(response: aiohttp.ClientResponse) -> object:
    """Decode a JSON response body, or return ``None`` when it is not valid."""
    try:
        return await response.json()
    except (aiohttp.ClientError, ValueError, TypeError):
        return None


class LLMClient:
    """Client that keeps one HTTP session and limits concurrent generations."""

    def __init__(self, settings: Settings | None = None) -> None:
        """Creates the client without opening a session."""
        self.session: aiohttp.ClientSession | None = None
        self._settings = settings
        self._semaphore: asyncio.Semaphore | None = None
        self._context_size: int | None = None
        self._token_counting_mode: str | None = None
        self._token_counting_lock = asyncio.Lock()

    def configure(self, settings: Settings) -> None:
        """Apply application settings before starting the client."""
        if self.session is not None and not self.session.closed:
            msg = "Cannot configure LLM client while its session is open"
            raise RuntimeError(msg)

        self._settings = settings
        self._semaphore = None
        self._context_size = None
        self._token_counting_mode = None

    @property
    def settings(self) -> Settings:
        """Return the explicitly supplied or process-wide settings."""
        if self._settings is not None:
            return self._settings
        return get_settings()

    @property
    def semaphore(self) -> asyncio.Semaphore:
        """Return the generation semaphore, creating it on first use."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(
                self.settings.LLM_MAX_CONCURRENT_GENERATIONS
            )
        return self._semaphore

    async def start(self) -> None:
        """Initialize the HTTP session."""
        await self._get_session()
        logger.info("LLM client initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        return await get_session(self)

    async def get_session(self) -> aiohttp.ClientSession:
        """Return the shared HTTP session."""
        return await self._get_session()

    def _server_url(self) -> str:
        return server_url(self.settings)

    def get_server_url(self) -> str:
        """Return the configured LLM server URL."""
        return self._server_url()

    @staticmethod
    def _normalize_messages(
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
        """Get the context size of the active model."""
        context_size = self._context_size
        if context_size is None:
            context_size = await fetch_context_size(self)
            self._context_size = context_size
        return context_size

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
        """Return the selected token counting mode."""
        configured_mode = self.settings.LLM_TOKEN_COUNTING
        if configured_mode != COUNTING_MODE_AUTO:
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
        """Count tokens using llama.cpp or a conservative estimate."""
        return await tokenize_messages(self, messages)

    async def count_text_tokens(self, text: str) -> int:
        """Count tokens in plain text."""
        return await tokenize_text(self, text)

    async def fit_messages_to_context(
        self,
        system_prompt: str,
        history: list[dict[str, Any]],
        user_message: object,
    ) -> list[dict[str, Any]]:
        """Fit the largest possible history into the model context."""
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
        """Delegate streaming generation to a separate module."""
        async for chunk in stream_unlimited(self, messages):
            yield chunk

    async def health_check(self) -> tuple[bool, str]:
        """Check the LLM server using /health or the standard /models endpoint."""
        try:
            return await self._probe_server()

        except TimeoutError:
            return False, texts.HEALTH_TIMEOUT

        except aiohttp.ClientError:
            return False, texts.HEALTH_SERVER_UNAVAILABLE

        except Exception:
            logger.exception("LLM health check failed")
            return False, texts.HEALTH_CHECK_ERROR

    async def _probe_server(self) -> tuple[bool, str]:
        """Probe /health first, then fall back to the /models endpoint."""
        session = await self._get_session()

        if await self._probe_health_endpoint(session):
            return True, texts.HEALTH_AVAILABLE

        return await self._probe_models_endpoint(session)

    async def _probe_health_endpoint(self, session: aiohttp.ClientSession) -> bool:
        """Return whether the optional /health endpoint reports ``ok``."""
        try:
            return await self._read_health_status(session)
        except (TimeoutError, aiohttp.ClientError):
            logger.debug("Optional LLM /health endpoint unavailable", exc_info=True)
            return False

    async def _read_health_status(self, session: aiohttp.ClientSession) -> bool:
        """Request /health and check for HTTP 200 with ``{"status": "ok"}``."""
        async with session.get(
            f"{self._server_url()}/health",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as response:
            if response.status != HTTPStatus.OK:
                return False
            data = await _json_or_none(response)
            return isinstance(data, dict) and data.get("status") == _HEALTH_OK_STATUS

    async def _probe_models_endpoint(
        self, session: aiohttp.ClientSession
    ) -> tuple[bool, str]:
        """Check /v1/models, the standard OpenAI endpoint.

        HTTP 200 means the API is available even if the server does not
        implement /health.
        """
        async with session.get(
            f"{self.settings.LLM_BASE_URL}/models",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as response:
            if response.status == HTTPStatus.OK:
                return True, texts.HEALTH_AVAILABLE
            return False, texts.HEALTH_API_UNAVAILABLE.format(status=response.status)

    async def close(self) -> None:
        """Close the HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()

        self.session = None
