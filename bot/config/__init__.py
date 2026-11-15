# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Совместимый публичный интерфейс конфигурации."""

from bot.config.env import (
    get_bool,
    get_float,
    get_int,
    get_log_level,
    get_optional_int,
    load_env_file,
    parse_ids,
)
from bot.config.paths import PROJECT_ROOT
from bot.config.prompts import load_default_system_prompt
from bot.config.settings import (
    Config,
    ConfigError,
    Settings,
    config,
    get_settings,
    load_settings,
    reset_settings_cache,
)

__all__ = [
    "PROJECT_ROOT",
    "Config",
    "ConfigError",
    "Settings",
    "config",
    "get_bool",
    "get_float",
    "get_int",
    "get_log_level",
    "get_optional_int",
    "get_settings",
    "load_default_system_prompt",
    "load_env_file",
    "load_settings",
    "parse_ids",
    "reset_settings_cache",
]
