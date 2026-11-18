# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Create the Telegram Bot/Dispatcher and start the application."""

import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher

from bot_obormot.app.lifecycle import run_application
from bot_obormot.app.logging_setup import configure_logging
from bot_obormot.app.routers import configure_dispatcher
from bot_obormot.config.token import is_valid_bot_token
from bot_obormot.env_readers import load_env_file
from bot_obormot.middlewares.correlation_id import CorrelationIdMiddleware
from bot_obormot.services.chat.aggregation import MessageAggregator
from bot_obormot.services.database import Database
from bot_obormot.services.llm.client import LLMClient
from bot_obormot.services.media.safety import configure_pillow_limits
from bot_obormot.settings import Settings, load_settings

logger = logging.getLogger("bot_obormot.main")


def log_access_mode(settings: Settings) -> None:
    """Log who can access the bot."""
    if settings.ALLOW_ALL_USERS:
        logger.warning("ACCESS MODE: open to everyone (ALLOW_ALL_USERS=true)")
    elif settings.ALLOWED_USERS:
        logger.info("ACCESS MODE: allowlist, %d users", len(settings.ALLOWED_USERS))
    else:
        logger.warning(
            "ACCESS MODE: only supervisor and administrators (ALLOWED_USERS is empty)"
        )


def create_bot(settings: Settings) -> Bot:
    """Create a Telegram Bot after validating its required token."""
    if not is_valid_bot_token(settings.BOT_TOKEN):
        msg = "BOT_TOKEN has an invalid format. Check .env"
        raise RuntimeError(msg)
    return Bot(token=settings.BOT_TOKEN)


def create_dispatcher(
    settings: Settings,
    llm_client: LLMClient,
    message_aggregator: MessageAggregator,
    database: Database,
) -> Dispatcher:
    """Create a Dispatcher and attach middleware and routers."""
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(CorrelationIdMiddleware())
    return configure_dispatcher(
        dispatcher, settings, llm_client, message_aggregator, database
    )


async def main(env_file: Path | None = None) -> None:
    """Run the application entry point."""
    os.umask(0o077)

    load_env_file(env_file)
    settings = load_settings(os.environ)

    configure_logging(settings)
    configure_pillow_limits()
    log_access_mode(settings)

    bot = create_bot(settings)
    llm_client = LLMClient(settings)
    message_aggregator = MessageAggregator()
    database = Database(settings)
    dispatcher = create_dispatcher(settings, llm_client, message_aggregator, database)
    await run_application(bot, dispatcher, llm_client, database)
