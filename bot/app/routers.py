"""Единственное место регистрации middleware и корневых роутеров."""

from aiogram import Dispatcher

from bot.handlers import admin, chat, commands, start
from bot.middlewares.access import AccessMiddleware
from bot.middlewares.throttle import ThrottleMiddleware
from bot.middlewares.temporary_messages import (
    TemporaryMessagesCleanupMiddleware,
)


def configure_dispatcher(dispatcher: Dispatcher) -> Dispatcher:
    """Подключает middleware и роутеры к уже созданному Dispatcher."""
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
