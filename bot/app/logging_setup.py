# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Настройка логирования приложения."""

import logging

from bot.config.settings import Settings
from bot.utils.log_filters import SecretsFilter

logger = logging.getLogger("bot.main")


def configure_logging(settings: Settings) -> None:
    """Настраивает корневое логирование с конфигурацией приложения."""
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    secrets_filter = SecretsFilter(
        [
            settings.BOT_TOKEN,
            settings.LLM_API_KEY,
            settings.WHISPER_API_KEY,
            settings.DOCUMENT_API_KEY,
        ]
    )

    # Фильтр на обработчиках применяется также к записям сторонних библиотек.
    for handler in logging.getLogger().handlers:
        handler.addFilter(secrets_filter)

    logger.info("Logging level: %s", settings.LOG_LEVEL)
