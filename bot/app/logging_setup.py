# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Настройка логирования приложения."""

import logging

from bot.log_context import CorrelationIdFilter
from bot.log_filters import SecretsFilter
from bot.settings import Settings

logger = logging.getLogger("bot.main")


def configure_logging(settings: Settings) -> None:
    """Настраивает корневое логирование с конфигурацией приложения."""
    correlation_field = "%(correlation_id)s"
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format=(
            "%(asctime)s | %(levelname)s | %(name)s | "
            f"{correlation_field} | %(message)s"
        ),
    )

    secrets_filter = SecretsFilter(
        [
            settings.BOT_TOKEN,
            settings.LLM_API_KEY,
            settings.AUDIODOC_AUDIO_KEY,
            settings.AUDIODOC_DOCUMENT_KEY,
        ]
    )
    correlation_filter = CorrelationIdFilter()

    # Handler filters also apply to records from third-party libraries.
    for handler in logging.getLogger().handlers:
        handler.addFilter(secrets_filter)
        handler.addFilter(correlation_filter)

    logger.info("Logging level: %s", settings.LOG_LEVEL)
    for old_name, new_name in settings.deprecated_env_vars:
        logger.warning(
            "Environment variable %s is deprecated; use %s instead",
            old_name,
            new_name,
        )
