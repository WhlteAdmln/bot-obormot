# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Configure application logging."""

import logging

from bot.log_context import CorrelationIdFilter
from bot.log_filters import SecretsFilter
from bot.settings import Settings

LOG_FORMAT = "%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s: %(message)s"

logger = logging.getLogger("bot.main")


def configure_logging(settings: Settings) -> None:
    """Configure root logging using application settings."""
    numeric_level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    logging.basicConfig(
        level=numeric_level,
        format=LOG_FORMAT,
    )

    root = logging.getLogger()
    root.setLevel(numeric_level)

    secret_filter = SecretsFilter(
        (
            settings.BOT_TOKEN,
            settings.LLM_API_KEY,
            settings.AUDIODOC_AUDIO_KEY,
            settings.AUDIODOC_DOCUMENT_KEY,
        )
    )
    for handler in root.handlers:
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        if not any(isinstance(item, CorrelationIdFilter) for item in handler.filters):
            handler.addFilter(CorrelationIdFilter())
        if not any(isinstance(item, SecretsFilter) for item in handler.filters):
            handler.addFilter(secret_filter)

    logger.info("Logging level: %s", settings.LOG_LEVEL)
    for old_name, new_name in settings.deprecated_env_vars:
        logger.warning(
            "Environment variable %s is deprecated; use %s instead",
            old_name,
            new_name,
        )
