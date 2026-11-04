"""Запуск ресурсов приложения, polling и корректное завершение."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.app.background.image_cleanup import periodic_image_cleanup
from bot.services.database import db
from bot.services.llm import llm_client

logger = logging.getLogger("bot.main")


async def run_application(bot: Bot, dispatcher: Dispatcher) -> None:
    """Подключает ресурсы, запускает polling и закрывает их в обратном порядке."""
    image_cleanup_task: asyncio.Task | None = None

    try:
        # Порядок старта является частью контракта приложения.
        await db.connect()
        logger.info("Database connected")

        await llm_client.start()
        logger.info("LLM client started")

        # Фоновая задача запускается только после подключения обоих ресурсов.
        image_cleanup_task = asyncio.create_task(
            periodic_image_cleanup(),
            name="image_cleanup",
        )
        logger.info("Image cleanup task started")
        logger.info("Telegram LLM bot started")

        await dispatcher.start_polling(
            bot,
            close_bot_session=False,
        )

    finally:
        logger.info("Shutting down bot...")

        # Сначала останавливаем и дожидаемся завершения фоновой очистки.
        if image_cleanup_task is not None:
            image_cleanup_task.cancel()
            await asyncio.gather(
                image_cleanup_task,
                return_exceptions=True,
            )
            logger.info("Image cleanup task stopped")

        cleanup_steps = [
            ("LLM client", llm_client.close),
            ("Database", db.close),
            ("Telegram session", bot.session.close),
        ]

        # Ошибка закрытия одного ресурса не мешает закрытию остальных.
        for name, cleanup in cleanup_steps:
            try:
                await cleanup()
                logger.info("%s closed", name)
            except Exception:
                logger.exception("Failed to close %s", name)

        logger.info("Bot stopped")
