# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Create and reuse the LLM client's HTTP session."""

from typing import Protocol

import aiohttp

from bot_obormot.settings import Settings


class SessionOwner(Protocol):
    """Object that keeps a reusable HTTP session."""

    session: aiohttp.ClientSession | None

    @property
    def settings(self) -> Settings:
        """Return the settings used by the client."""
        ...


def _auth_headers(settings: Settings) -> dict[str, str]:
    """Return the authorization header when an API key is configured."""
    api_key = (settings.LLM_API_KEY or "").strip()

    if not api_key or api_key == "not-needed":
        return {}

    return {"Authorization": f"Bearer {api_key}"}


async def get_session(client: SessionOwner) -> aiohttp.ClientSession:
    """Return the open HTTP session, creating it when necessary."""
    if client.session is None or client.session.closed:
        settings = client.settings
        timeout = aiohttp.ClientTimeout(total=settings.LLM_TIMEOUT)
        client.session = aiohttp.ClientSession(
            timeout=timeout,
            headers=_auth_headers(settings),
        )

    return client.session
