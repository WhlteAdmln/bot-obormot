"""Router aggregator for history, prompt, limits, and fallback commands."""

from aiogram import Router

from bot.handlers.fallback import handler as fallback
from bot.handlers.history import basic as history_basic
from bot.handlers.history import limits as history_limits
from bot.handlers.prompt import handler as prompt

router = Router()
router.include_router(history_basic.router)
router.include_router(prompt.router)
router.include_router(history_limits.router)
router.include_router(fallback.router)

__all__ = ["router"]
