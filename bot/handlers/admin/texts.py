# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Russian text displayed by administrator handlers."""

TELEGRAM_UNAVAILABLE = "Недоступен"
TELEGRAM_AVAILABLE = "Доступен"
DATABASE_CONNECTION_ERROR = "Ошибка подключения"
DATABASE_CONNECTED = "Подключена"
ADMIN_PERMISSION_CHECK_FAILED = "⚠️ Не удалось проверить права администратора."
ACCESS_DENIED = "⛔ Доступ запрещён."
DATABASE_STATUS_LABEL = "База данных"
INFERENCE_STATUS_LABEL = "Инференс"
HEALTH_CHECK_IN_PROGRESS = "🔎 Проверяю состояние компонентов..."
HEALTH_REPORT_TITLE = "🩺 <b>Состояние бота</b>\n\n"
ADMIN_PANEL_TITLE = "🛠 Панель управления\n\n"
ADMIN_PANEL_ADMIN_COUNT = "👥 Обычных администраторов: {count}\n"
ADMIN_PANEL_ALLOWLIST_COUNT = "🔐 Пользователей в allowlist: {count}\n\n"
ADMIN_PANEL_COMMANDS_TITLE = "Команды управления:\n"
ADMIN_PANEL_ADMINS_COMMAND = "/admins — список администраторов\n"
ADMIN_PANEL_ADMIN_ADD_COMMAND = "/admin_add ID — добавить администратора\n"
ADMIN_PANEL_ADMIN_REMOVE_COMMAND = "/admin_remove ID — удалить администратора"
ADMIN_LIST_TITLE = "👥 Список администраторов\n\n👑 Supervisor: {supervisor_id}\n"
ADMIN_LIST_REGULAR_TITLE = "\nОбычные администраторы:\n"
ADMIN_LIST_EMPTY = "\nОбычных администраторов пока нет."
ADMIN_ID_PROMPT = "Укажи Telegram ID пользователя.\nПример: /{command} 123456789"
TELEGRAM_ID_INTEGER_REQUIRED = "⛔ Telegram ID должен быть целым числом."
TELEGRAM_ID_POSITIVE_REQUIRED = "⛔ Telegram ID должен быть положительным числом."
ALREADY_SUPERVISOR = "ℹ️ Этот пользователь уже является Supervisor."
ADMIN_ADDED = "✅ Пользователь {user_id} добавлен в список администраторов."
ADMIN_ALREADY_EXISTS = "ℹ️ Пользователь {user_id} уже является администратором."
SUPERVISOR_CANNOT_BE_REMOVED = "⛔ Нельзя удалить Supervisor."
ADMIN_REMOVED = "✅ Пользователь {user_id} удалён из списка администраторов."
ADMIN_NOT_FOUND = "ℹ️ Пользователь {user_id} не найден среди администраторов."
TARGET_ID_PROMPT = "Укажи положительный Telegram ID. Пример: /{command} 123456789"

_BAN_PROTECTED_TARGET_SUFFIX = "Сначала сними права администратора."
BAN_PROTECTED_TARGET = (
    "⛔ Этого пользователя заблокировать нельзя. " + _BAN_PROTECTED_TARGET_SUFFIX
)

USER_BANNED = "✅ Пользователь {target_id} заблокирован."
USER_ALREADY_BANNED = "ℹ️ Пользователь {target_id} уже заблокирован."
USER_UNBANNED = "✅ Блокировка пользователя {target_id} снята."
USER_NOT_BANNED = "ℹ️ Пользователь {target_id} не был заблокирован."
