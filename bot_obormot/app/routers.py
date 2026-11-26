# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Register application middleware and root routers."""

from aiogram import Dispatcher

from bot_obormot.handlers import admin, routers, start
from bot_obormot.handlers.chat import handler as chat
from bot_obormot.handlers.chat.handler import ChatRuntime
from bot_obormot.middlewares.access import AccessMiddleware
from bot_obormot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)
from bot_obormot.middlewares.throttle import ThrottleMiddleware
from bot_obormot.services.chat.aggregation import MessageAggregator
from bot_obormot.services.chat.locks import UserLocks
from bot_obormot.services.database import Database
from bot_obormot.services.llm.client import LLMClient
from bot_obormot.services.media import MediaSlots
from bot_obormot.services.telegram import TelegramDownloader
from bot_obormot.settings import Settings, get_settings


def configure_dispatcher(
    dispatcher: Dispatcher,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    message_aggregator: MessageAggregator | None = None,
    database: Database | None = None,
    user_locks: UserLocks | None = None,
) -> Dispatcher:
    """Attach middleware and routers to the configured Dispatcher."""
    if settings is None:
        settings = get_settings()
    dispatcher.workflow_data["settings"] = settings
    if llm_client is not None:
        dispatcher.workflow_data["llm_client"] = llm_client
    if message_aggregator is None:
        message_aggregator = MessageAggregator()
    if database is not None:
        dispatcher.workflow_data["database"] = database
    if user_locks is None:
        user_locks = UserLocks()
    # One downloader and one set of media slots per bot keep their limits
    # in the bot's event loop.
    dispatcher.workflow_data["chat_runtime"] = ChatRuntime(
        message_aggregator=message_aggregator,
        user_locks=user_locks,
        downloader=TelegramDownloader(),
        media_slots=MediaSlots(),
    )

    # Apply throttling first, then check access
    # and clean up temporary messages.
    dispatcher.message.middleware(ThrottleMiddleware())
    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.message.middleware(TemporaryMessagesCleanupMiddleware())

    # Router order matters: the general chat router must be last.
    dispatcher.include_router(start.create_router())
    dispatcher.include_router(admin.create_router())
    dispatcher.include_router(routers.create_router())
    dispatcher.include_router(chat.create_router())

    return dispatcher
