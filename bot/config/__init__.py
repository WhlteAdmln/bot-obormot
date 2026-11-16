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

__all__ = [
    "PROJECT_ROOT",
    "get_bool",
    "get_float",
    "get_int",
    "get_log_level",
    "get_optional_int",
    "load_default_system_prompt",
    "load_env_file",
    "parse_ids",
]
