# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Russian text displayed by prompt handlers."""

PROMPT_TRUNCATION_SUFFIX = "\n\n... (промпт сокращён при отображении)"
PERSONAL_PROMPT_SOURCE = "👤 Персональный"
DEFAULT_PROMPT_SOURCE = "📄 Стандартный"

PROMPT_DISPLAY_TEMPLATE = """Текущий системный промпт
Источник: {source}

{prompt}

Изменить:
/prompt_set

Сбросить персональный промпт:
/prompt_reset"""

PROMPT_INPUT_TEMPLATE = """✍️ Отправь следующим сообщением новый системный промпт.

Максимальная длина — {max_length} символов.
Для отмены используй /cancel."""

PROMPT_EMPTY_ERROR = "Промпт не может быть пустым. Попробуй ещё раз."
PROMPT_TOO_LONG_ERROR = "Промпт слишком длинный. Максимум {max_length} символов."
PROMPT_SAVED = """✅ Персональный системный промпт сохранён.

Теперь он используется только в твоём чате."""
# pylint counts the two code points of the emoji, ruff counts its display width.
PROMPT_RESET_ALREADY_DEFAULT = "ℹ️ У тебя уже используется стандартный системный промпт."  # pylint: disable=line-too-long
PROMPT_RESET_DONE = """🔄 Персональный системный промпт удалён.
Теперь используется стандартный промпт."""
PROMPT_CANCELLED = "❎ Ввод системного промпта отменён."
