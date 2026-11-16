# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Russian text displayed by history handlers."""

HISTORY_CLEARED = "🧹 История диалога очищена."
USER_DATA_DELETED = "🧹 Все твои данные удалены."
HISTORY_LIMIT_STATUS = """📚 Твой лимит истории: {current_limit} полных обменов.
Стандартный лимит: {default_limit}."""

OWN_LIMIT_INTEGER_REQUIRED = """⚠️ Укажи целое число.
Пример: /history_limit 20"""
HISTORY_LIMIT_RANGE = "⚠️ Допустимый лимит: от 1 до {maximum}."
OWN_LIMIT_UPDATED = "✅ Твой лимит истории установлен: {exchange_limit} полных обменов."

TARGET_LIMIT_ADMIN_REQUIRED = (
    "⛔ Назначать лимиты другим пользователям могут только администраторы."
)
TARGET_LIMIT_ARGUMENTS_INVALID = (
    "⚠️ Укажи корректный ID пользователя и целое число лимита."
)
TARGET_USER_ID_POSITIVE_REQUIRED = "⚠️ ID пользователя должен быть положительным."
TARGET_LIMIT_UPDATED = "✅ Для пользователя %s установлен лимит %s полных обменов."

HISTORY_LIMIT_USAGE = """Использование:
/history — показать текущий лимит
/history_limit 20 — установить свой лимит
/history_limit ID 100 — установить лимит другому пользователю (только администратор)."""

HISTORY_LIMIT_TOO_MANY_ARGUMENTS = """⚠️ Слишком много аргументов.
Пример: /history_limit 20 или /history_limit ID 100."""
