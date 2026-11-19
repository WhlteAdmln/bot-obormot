# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Configuration helpers; settings live in :mod:`bot_obormot.settings`."""

from bot_obormot.config.prompts import load_default_system_prompt
from bot_obormot.env_readers import load_env_file

__all__ = [
    "load_default_system_prompt",
    "load_env_file",
]
