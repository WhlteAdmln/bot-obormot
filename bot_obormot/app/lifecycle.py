# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Start application resources, run polling, and shut down cleanly."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot_obormot.app.background.image_cleanup import periodic_image_cleanup
from bot_obormot.services.database import Database
from bot_obormot.services.llm.client import LLMClient

logger = logging.getLogger("bot_obormot.main")


async def run_application(
    bot: Bot,
    dispatcher: Dispatcher,
    llm_client: LLMClient,
    database: Database,
) -> None:
    """Start polling and close resources in reverse order."""
    image_cleanup_task: asyncio.Task[None] | None = None

    try:
        async with database:
            logger.info("Database connected")

            await llm_client.start()
            logger.info("LLM client started")

            image_cleanup_task = asyncio.create_task(
                periodic_image_cleanup(database),
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

        if image_cleanup_task is not None:
            image_cleanup_task.cancel()
            await asyncio.gather(
                image_cleanup_task,
                return_exceptions=True,
            )
            logger.info("Image cleanup task stopped")

        cleanup_steps = [
            ("LLM client", llm_client.close),
            ("Telegram session", bot.session.close),
        ]

        for name, cleanup in cleanup_steps:
            try:
                await cleanup()
                logger.info("%s closed", name)
            except Exception:
                logger.exception("Failed to close %s", name)

        logger.info("Bot stopped")
