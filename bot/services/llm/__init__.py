# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Публичный API LLM-сервиса с сохранением прежних импортов."""

from bot.services.llm.client import LLMClient, llm_client
from bot.services.llm.constants import CONTEXT_SAFETY_MARGIN, IMAGE_TOKEN_RESERVE

__all__ = [
    "CONTEXT_SAFETY_MARGIN",
    "IMAGE_TOKEN_RESERVE",
    "LLMClient",
    "llm_client",
]
