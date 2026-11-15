# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Запуск ресурсов приложения, polling и корректное завершение."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.app.background.image_cleanup import periodic_image_cleanup
from bot.config.settings import Settings
from bot.services.database import Database, db
from bot.services.llm.client import LLMClient

logger = logging.getLogger("bot.main")


async def run_application(
    bot: Bot,
    dispatcher: Dispatcher,
    settings: Settings,
    llm_client: LLMClient,
    database: Database,
) -> None:
    """Подключает ресурсы, запускает polling и закрывает их в обратном порядке."""
    image_cleanup_task: asyncio.Task[None] | None = None

    try:
        # Keep the legacy database connected for components not yet migrated.
        db.configure(settings)
        await db.connect()
        logger.info("Legacy database connected")

        async with database:
            logger.info("Database connected")

            await llm_client.start()
            logger.info("LLM client started")

            # The legacy cleanup task still uses the module-level database.
            image_cleanup_task = asyncio.create_task(
                periodic_image_cleanup(),
                name="image_cleanup",
            )
            try:
                logger.info("Image cleanup task started")
                logger.info("Telegram LLM bot started")

                await dispatcher.start_polling(
                    bot,
                    close_bot_session=False,
                )
            finally:
                image_cleanup_task.cancel()
                await asyncio.gather(
                    image_cleanup_task,
                    return_exceptions=True,
                )
                image_cleanup_task = None
                logger.info("Image cleanup task stopped")

    finally:
        logger.info("Shutting down bot...")

        # Keep a fallback for failures before the task's inner cleanup block.
        if image_cleanup_task is not None:
            image_cleanup_task.cancel()
            await asyncio.gather(
                image_cleanup_task,
                return_exceptions=True,
            )
            logger.info("Image cleanup task stopped")

        cleanup_steps = [
            ("LLM client", llm_client.close),
            ("Legacy database", db.close),
            ("Telegram session", bot.session.close),
        ]

        for name, cleanup in cleanup_steps:
            try:
                await cleanup()
                logger.info("%s closed", name)
            except Exception:
                logger.exception("Failed to close %s", name)

        logger.info("Bot stopped")
