"""Настройка логирования приложения."""

import logging

from bot.config import config

logger = logging.getLogger("bot.main")


def configure_logging() -> None:
    """Настраивает корневое логирование с конфигурацией приложения."""
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger.info("Logging level: %s", config.LOG_LEVEL)
