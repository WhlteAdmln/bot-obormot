# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Register application middleware and root routers."""

from aiogram import Dispatcher

from bot_obormot.handlers import admin, routers, start
from bot_obormot.handlers.chat import handler as chat
from bot_obormot.middlewares.access import AccessMiddleware
from bot_obormot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)
from bot_obormot.middlewares.throttle import ThrottleMiddleware
from bot_obormot.services.chat.aggregation import MessageAggregator
from bot_obormot.services.chat.locks import UserLocks
from bot_obormot.services.database import Database
from bot_obormot.services.llm.client import LLMClient
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
    dispatcher.workflow_data["message_aggregator"] = message_aggregator
    if database is not None:
        dispatcher.workflow_data["database"] = database
    if user_locks is None:
        user_locks = UserLocks()
    dispatcher.workflow_data["user_locks"] = user_locks

    # Apply throttling first, then check access
    # and clean up temporary messages.
    dispatcher.message.middleware(ThrottleMiddleware())
    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.message.middleware(TemporaryMessagesCleanupMiddleware())

    # Router order matters: the general chat router must be last.
    dispatcher.include_router(start.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(routers.router)
    dispatcher.include_router(chat.router)

    return dispatcher
