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
from bot.config.env import load_env_file
from bot.config.settings import Settings, load_settings
from bot.services.chat.aggregation import MessageAggregator
from bot.services.llm.client import LLMClient
from bot.services.media.safety import configure_pillow_limits

logger = logging.getLogger("bot.main")


def log_access_mode(settings: Settings) -> None:
    """Пишет в лог, кто может пользоваться ботом."""
    if settings.ALLOW_ALL_USERS:
        logger.warning("ACCESS MODE: open to everyone (ALLOW_ALL_USERS=true)")
    elif settings.ALLOWED_USERS:
        logger.info("ACCESS MODE: allowlist, %d users", len(settings.ALLOWED_USERS))
    else:
        logger.warning(
            "ACCESS MODE: only supervisor and administrators (ALLOWED_USERS is empty)"
        )


def create_bot(settings: Settings) -> Bot:
    """Создаёт Telegram Bot после проверки обязательного токена."""
    if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{30,}", settings.BOT_TOKEN):
        msg = "BOT_TOKEN имеет неверный формат. Проверьте .env"
        raise RuntimeError(msg)
    return Bot(token=settings.BOT_TOKEN)


def create_dispatcher(
    settings: Settings,
    llm_client: LLMClient,
    message_aggregator: MessageAggregator,
) -> Dispatcher:
    """Создаёт Dispatcher и подключает к нему middleware и роутеры."""
    return configure_dispatcher(Dispatcher(), settings, llm_client, message_aggregator)


async def main() -> None:
    """Точка сборки приложения."""
    os.umask(0o077)

    load_env_file()
    settings = load_settings(os.environ)

    configure_logging(settings)
    configure_pillow_limits()
    log_access_mode(settings)

    bot = create_bot(settings)
    llm_client = LLMClient(settings)
    message_aggregator = MessageAggregator()
    dispatcher = create_dispatcher(settings, llm_client, message_aggregator)
    await run_application(bot, dispatcher, settings, llm_client)
