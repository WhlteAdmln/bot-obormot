# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Единственное место регистрации middleware и корневых роутеров."""

from aiogram import Dispatcher

from bot.config.settings import Settings, get_settings
from bot.handlers import admin, chat, commands, start
from bot.middlewares.access import AccessMiddleware
from bot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)
from bot.middlewares.throttle import ThrottleMiddleware
from bot.services.chat.aggregation import MessageAggregator
from bot.services.database import Database
from bot.services.llm.client import LLMClient


def configure_dispatcher(
    dispatcher: Dispatcher,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    message_aggregator: MessageAggregator | None = None,
    database: Database | None = None,
) -> Dispatcher:
    """Подключает middleware и роутеры к уже созданному Dispatcher."""
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

    # Сначала ограничиваем частоту событий, затем проверяем доступ
    # и очищаем временные сообщения.
    dispatcher.message.middleware(ThrottleMiddleware())
    dispatcher.message.middleware(AccessMiddleware())
    dispatcher.message.middleware(TemporaryMessagesCleanupMiddleware())

    # Порядок роутеров важен: общий chat router должен идти последним.
    dispatcher.include_router(start.router)
    dispatcher.include_router(admin.router)
    dispatcher.include_router(commands.router)
    dispatcher.include_router(chat.router)

    return dispatcher
