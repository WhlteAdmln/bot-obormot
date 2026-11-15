# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Создание и повторное использование HTTP-сессии LLM-клиента."""

from typing import Protocol

import aiohttp

from bot.config import config


class SessionOwner(Protocol):
    """Object that keeps a reusable HTTP session."""

    session: aiohttp.ClientSession | None


def _auth_headers() -> dict[str, str]:
    """Возвращает заголовок авторизации, если ключ задан."""
    api_key = (config.LLM_API_KEY or "").strip()

    if not api_key or api_key == "not-needed":
        return {}

    return {"Authorization": f"Bearer {api_key}"}


async def get_session(client: SessionOwner) -> aiohttp.ClientSession:
    """Возвращает открытую HTTP-сессию, создавая её при необходимости."""
    if client.session is None or client.session.closed:
        timeout = aiohttp.ClientTimeout(total=config.LLM_TIMEOUT)
        client.session = aiohttp.ClientSession(
            timeout=timeout,
            headers=_auth_headers(),
        )

    return client.session
