"""Совместимый публичный интерфейс конфигурации."""

from dotenv import load_dotenv

from bot.config.paths import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

from bot.config.env import get_float, get_int, get_log_level, parse_ids  # noqa: E402
from bot.config.prompts import load_default_system_prompt  # noqa: E402
from bot.config.settings import Config, config  # noqa: E402

__all__ = [
    "Config",
    "config",
    "get_int",
    "get_float",
    "get_log_level",
    "parse_ids",
    "PROJECT_ROOT",
    "load_default_system_prompt",
]
