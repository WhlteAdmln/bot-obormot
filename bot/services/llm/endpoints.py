# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build URLs for special LLM server endpoints."""

from bot.settings import Settings, get_settings


def server_url(settings: Settings | None = None) -> str:
    """Return the server root URL without the OpenAI API `/v1` suffix."""
    if settings is None:
        settings = get_settings()
    return settings.LLM_BASE_URL.rstrip("/").removesuffix("/v1")
