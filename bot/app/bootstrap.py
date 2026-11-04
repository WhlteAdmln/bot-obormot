"""Создание Telegram Bot/Dispatcher и запуск приложения."""

import logging

from aiogram import Bot, Dispatcher

from bot.app.lifecycle import run_application
from bot.app.logging_setup import configure_logging
from bot.app.routers import configure_dispatcher
from bot.config import config

logger = logging.getLogger("bot.main")


def create_bot() -> Bot:
    """Создаёт Telegram Bot после проверки обязательного токена."""
    if not config.BOT_TOKEN or config.BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN":
        raise RuntimeError("Укажи настоящий BOT_TOKEN в файле .env")
    return Bot(token=config.BOT_TOKEN)


def create_dispatcher() -> Dispatcher:
    """Создаёт Dispatcher и подключает к нему middleware и роутеры."""
    return configure_dispatcher(Dispatcher())


async def main() -> None:
    """Точка сборки приложения."""
    configure_logging()
    bot = create_bot()
    dispatcher = create_dispatcher()
    await run_application(bot, dispatcher)
