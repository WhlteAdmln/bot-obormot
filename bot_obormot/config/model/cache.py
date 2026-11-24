# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""The process-wide settings cache."""

import os
from functools import lru_cache

from bot_obormot.config.model.loader import load_settings
from bot_obormot.config.model.schema import Settings


@lru_cache(maxsize=1)
def _load_cached_settings() -> Settings:
    return load_settings(os.environ)


def get_settings() -> Settings:
    """Return the process-wide cached settings."""
    return _load_cached_settings()


def reset_settings_cache() -> None:
    """Clear cached settings."""
    _load_cached_settings.cache_clear()
