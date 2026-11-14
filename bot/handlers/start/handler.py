# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Handler of the /start command."""

import logging
from typing import TYPE_CHECKING, Any, cast

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    Message,
)

from bot.config import config
from bot.fsm.keys import WELCOME_MESSAGE_KEY
from bot.services.database import db

if TYPE_CHECKING:
    from aiogram import Bot

router = Router()
logger = logging.getLogger("bot.handlers.start")


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Registers the command menu for the user and sends the welcome message."""
    if message.from_user is None:
        return

    user_id = message.from_user.id

    # Supervisor всегда имеет доступ к административным функциям.
    is_admin = user_id == config.SUPERVISOR_ID

    # Проверяем обычных администраторов через SQLite.
    if not is_admin:
        try:
            admin_ids = await db.get_admin_ids()
            is_admin = user_id in admin_ids

        except Exception:
            logger.exception("Could not load administrators for the /start menu")
            is_admin = False

    # Формируем индивидуальное меню команд Telegram.
    commands = [
        BotCommand(command="start", description="Показать справку"),
        BotCommand(command="history", description="Показать лимит истории"),
        BotCommand(command="history_limit", description="Изменить лимит истории"),
        BotCommand(command="history_clear", description="Очистить историю диалога"),
        BotCommand(command="forget_me", description="Удалить все свои данные"),
        BotCommand(command="prompt", description="Показать системный промпт"),
        BotCommand(command="prompt_set", description="Установить системный промпт"),
        BotCommand(command="prompt_reset", description="Сбросить системный промпт"),
        BotCommand(command="cancel", description="Отменить ввод промпта"),
    ]

    if is_admin:
        commands.extend(
            [
                BotCommand(
                    command="health",
                    description="Проверить состояние бота",
                ),
                BotCommand(
                    command="ban",
                    description="Заблокировать пользователя",
                ),
                BotCommand(
                    command="unban",
                    description="Снять блокировку пользователя",
                ),
            ]
        )

    # Управление администраторами доступно только Supervisor.
    if user_id == config.SUPERVISOR_ID:
        commands.extend(
            [
                BotCommand(
                    command="admin",
                    description="Панель управления",
                ),
                BotCommand(
                    command="admins",
                    description="Список администраторов",
                ),
                BotCommand(
                    command="admin_add",
                    description="Добавить администратора",
                ),
                BotCommand(
                    command="admin_remove",
                    description="Удалить администратора",
                ),
            ]
        )

    bot = cast("Bot", message.bot)
    await bot.set_my_commands(
        commands=commands,
        scope=BotCommandScopeChat(chat_id=message.chat.id),
    )

    text = (
        "Привет! 👋 Я бот для работы с LLM в формате чата.\n\n"
        "📋 Мои команды:\n"
        "/start — показать справку\n"
        "/history — показать текущий лимит истории\n"
        "/history_limit ЧИСЛО — изменить свой лимит\n"
        "/history_clear — очистить историю диалога\n\n"
        "/forget_me — удалить все свои данные\n\n"
        "🧠 Системный промпт:\n"
        "/prompt — показать текущий промпт\n"
        "/prompt_set — установить персональный промпт\n"
        "/prompt_reset — сбросить персональный промпт\n"
        "/cancel — отменить ввод промпта\n\n"
    )

    if is_admin:
        text += (
            "🩺 Состояние бота:\n"
            "/health — проверить состояние компонентов\n\n"
            "📚 Управление историей:\n"
            f"/history_limit ЧИСЛО — изменить свой лимит "
            f"(до {config.MAX_HISTORY_EXCHANGES})\n"
            "/history_limit ID ЧИСЛО — изменить лимит пользователя\n"
            "/ban ID — заблокировать пользователя\n"
            "/unban ID — снять блокировку пользователя\n\n"
        )

    # Блок управления администраторами видит только Supervisor.
    if user_id == config.SUPERVISOR_ID:
        text += (
            "🛠 Управление администраторами:\n"
            "/admin — панель управления\n"
            "/admins — список администраторов\n"
            "/admin_add ID — добавить администратора\n"
            "/admin_remove ID — удалить администратора\n\n"
        )

    text += (
        "✨ Что я умею:\n"
        "💬 Общаться с помощью локальной языковой модели.\n"
        "🎤 Распознавать голосовые сообщения и аудио.\n"
        "🖼 Анализировать фотографии и изображения.\n"
        "🎬 Анализировать видео.\n"
        "🎞 Обрабатывать GIF и анимированные стикеры.\n"
        "📄 Читать документы PDF, DOCX, XLSX, PPTX и другие форматы.\n"
        "🔍 Распознавать текст в сканированных документах.\n\n"
        "Чтобы начать, просто напиши мне 😉"
    )

    response = await message.answer(text)

    data: dict[str, Any] = {WELCOME_MESSAGE_KEY: response.message_id}
    await state.update_data(**data)
