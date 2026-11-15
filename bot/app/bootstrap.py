# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Создание Telegram Bot/Dispatcher и запуск приложения."""

import logging
import os
import re

from aiogram import Bot, Dispatcher

from bot.app.lifecycle import run_application
from bot.app.logging_setup import configure_logging
from bot.app.routers import configure_dispatcher
from bot.config import config
from bot.services.media.safety import configure_pillow_limits

logger = logging.getLogger("bot.main")


def log_access_mode() -> None:
    """Пишет в лог, кто может пользоваться ботом."""
    if config.ALLOW_ALL_USERS:
        logger.warning("ACCESS MODE: open to everyone (ALLOW_ALL_USERS=true)")
    elif config.ALLOWED_USERS:
        logger.info("ACCESS MODE: allowlist, %d users", len(config.ALLOWED_USERS))
    else:
        logger.warning(
            "ACCESS MODE: only supervisor and administrators (ALLOWED_USERS is empty)"
        )


def create_bot() -> Bot:
    """Создаёт Telegram Bot после проверки обязательного токена."""
    if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", config.BOT_TOKEN):
        msg = "BOT_TOKEN имеет неверный формат. Проверьте .env"
        raise RuntimeError(msg)
    return Bot(token=config.BOT_TOKEN)


def create_dispatcher() -> Dispatcher:
    """Создаёт Dispatcher и подключает к нему middleware и роутеры."""
    return configure_dispatcher(Dispatcher())


async def main() -> None:
    """Точка сборки приложения."""
    os.umask(0o077)
    configure_logging()
    configure_pillow_limits()
    log_access_mode()
    bot = create_bot()
    dispatcher = create_dispatcher()
    await run_application(bot, dispatcher)
