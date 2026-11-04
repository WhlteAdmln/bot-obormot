"""Совместимый публичный интерфейс конфигурации."""

from dotenv import load_dotenv

load_dotenv()

from bot.config.env import get_float, get_int, get_log_level, parse_ids
from bot.config.paths import PROJECT_ROOT
from bot.config.prompts import load_default_system_prompt
from bot.config.settings import Config, config

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
