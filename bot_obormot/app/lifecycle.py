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


async def _poll_with_cleanup_task(
    bot: Bot,
    dispatcher: Dispatcher,
    database: Database,
) -> None:
    """Run polling next to the periodic image cleanup task and stop the task."""
    image_cleanup_task = asyncio.create_task(
        periodic_image_cleanup(database),
        name="image_cleanup",
    )
    logger.info("Image cleanup task started")
    logger.info("Telegram LLM bot started")
    try:
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
        logger.info("Image cleanup task stopped")


async def _run_with_database(
    bot: Bot,
    dispatcher: Dispatcher,
    llm_client: LLMClient,
    database: Database,
) -> None:
    """Connect the database, start the LLM client, and poll until stopped."""
    async with database:
        logger.info("Database connected")

        await llm_client.start()
        logger.info("LLM client started")

        await _poll_with_cleanup_task(bot, dispatcher, database)


async def _close_resources(bot: Bot, llm_client: LLMClient) -> None:
    """Close the LLM client and the Telegram session, logging each failure."""
    cleanup_steps = [
        ("LLM client", llm_client.close),
        ("Telegram session", bot.session.close),
    ]

    for name, cleanup in cleanup_steps:
        try:
            await cleanup()
        except Exception:
            logger.exception("Failed to close %s", name)
        else:
            logger.info("%s closed", name)


async def run_application(
    bot: Bot,
    dispatcher: Dispatcher,
    llm_client: LLMClient,
    database: Database,
) -> None:
    """Start polling and close resources in reverse order."""
    try:
        await _run_with_database(bot, dispatcher, llm_client, database)
    finally:
        logger.info("Shutting down bot...")
        await _close_resources(bot, llm_client)
        logger.info("Bot stopped")
