# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Router aggregator for history, prompt, limits, and fallback commands."""

from aiogram import Router

from bot_obormot.handlers.fallback import handler as fallback
from bot_obormot.handlers.history import basic as history_basic
from bot_obormot.handlers.history import limits as history_limits
from bot_obormot.handlers.prompt import handler as prompt


def create_router() -> Router:
    """Build a router with the history, prompt, limits and fallback routers."""
    router = Router()
    router.include_router(history_basic.create_router())
    router.include_router(prompt.create_router())
    router.include_router(history_limits.create_router())
    router.include_router(fallback.create_router())
    return router


__all__ = ["create_router"]
