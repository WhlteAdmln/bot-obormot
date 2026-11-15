# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Построение URL-адресов специальных endpoint-ов LLM-сервера."""

from bot.config import config


def server_url() -> str:
    """Возвращает корневой URL сервера без суффикса OpenAI API `/v1`."""
    return config.LLM_BASE_URL.rstrip("/").removesuffix("/v1")
