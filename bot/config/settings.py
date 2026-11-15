# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Compatibility exports for the application settings."""

from bot.config.model import (
    ConfigError,
    Settings,
    config,
    get_settings,
    load_settings,
    reset_settings_cache,
)

Config = Settings

__all__ = [
    "Config",
    "ConfigError",
    "Settings",
    "config",
    "get_settings",
    "load_settings",
    "reset_settings_cache",
]
