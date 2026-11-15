# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Настройка логирования приложения."""

import logging

from bot.config import config
from bot.utils.log_filters import SecretsFilter

logger = logging.getLogger("bot.main")


def configure_logging() -> None:
    """Настраивает корневое логирование с конфигурацией приложения."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    secrets_filter = SecretsFilter(
        [
            config.BOT_TOKEN,
            config.LLM_API_KEY,
            getattr(config, "WHISPER_API_KEY", ""),
            getattr(config, "DOCUMENT_API_KEY", ""),
        ]
    )

    # Фильтр на обработчиках применяется также к записям сторонних библиотек.
    for handler in logging.getLogger().handlers:
        handler.addFilter(secrets_filter)

    logger.info("Logging level: %s", config.LOG_LEVEL)
