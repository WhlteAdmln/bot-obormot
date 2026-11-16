# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Russian text displayed by the start handler."""

START_COMMAND_DESCRIPTION = "Показать справку"
HISTORY_COMMAND_DESCRIPTION = "Показать лимит истории"
HISTORY_LIMIT_COMMAND_DESCRIPTION = "Изменить лимит истории"
HISTORY_CLEAR_COMMAND_DESCRIPTION = "Очистить историю диалога"
FORGET_ME_COMMAND_DESCRIPTION = "Удалить все свои данные"
PROMPT_COMMAND_DESCRIPTION = "Показать системный промпт"
PROMPT_SET_COMMAND_DESCRIPTION = "Установить системный промпт"
PROMPT_RESET_COMMAND_DESCRIPTION = "Сбросить системный промпт"
CANCEL_COMMAND_DESCRIPTION = "Отменить ввод промпта"
HEALTH_COMMAND_DESCRIPTION = "Проверить состояние бота"
BAN_COMMAND_DESCRIPTION = "Заблокировать пользователя"
UNBAN_COMMAND_DESCRIPTION = "Снять блокировку пользователя"
ADMIN_COMMAND_DESCRIPTION = "Панель управления"
ADMINS_COMMAND_DESCRIPTION = "Список администраторов"
ADMIN_ADD_COMMAND_DESCRIPTION = "Добавить администратора"
ADMIN_REMOVE_COMMAND_DESCRIPTION = "Удалить администратора"

WELCOME_MESSAGE = (
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

ADMIN_HELP_MESSAGE = (
    "🩺 Состояние бота:\n"
    "/health — проверить состояние компонентов\n\n"
    "📚 Управление историей:\n"
    "/history_limit ЧИСЛО — изменить свой лимит "
    "(до {max_history_exchanges})\n"
    "/history_limit ID ЧИСЛО — изменить лимит пользователя\n"
    "/ban ID — заблокировать пользователя\n"
    "/unban ID — снять блокировку пользователя\n\n"
)

SUPERVISOR_HELP_MESSAGE = (
    "🛠 Управление администраторами:\n"
    "/admin — панель управления\n"
    "/admins — список администраторов\n"
    "/admin_add ID — добавить администратора\n"
    "/admin_remove ID — удалить администратора\n\n"
)

CAPABILITIES_MESSAGE = (
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
