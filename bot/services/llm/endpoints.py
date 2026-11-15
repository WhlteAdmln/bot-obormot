# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Построение URL-адресов специальных endpoint-ов LLM-сервера."""

from bot.config.settings import Settings, get_settings


def server_url(settings: Settings | None = None) -> str:
    """Возвращает корневой URL сервера без суффикса OpenAI API `/v1`."""
    if settings is None:
        settings = get_settings()
    return settings.LLM_BASE_URL.rstrip("/").removesuffix("/v1")
