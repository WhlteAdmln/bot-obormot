# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Factories for isolated application settings in tests."""

from dataclasses import replace
from typing import Any, cast

from bot_obormot.settings import Settings


def make_settings(**overrides: object) -> Settings:
    """Build test settings with optional field overrides."""
    defaults = Settings(
        BOT_TOKEN="123456789:" + "A" * 35,
        LOG_LEVEL="WARNING",
        SUPERVISOR_ID=999999999,
        DATABASE_PATH="data/test-bot.db",
        LLM_BASE_URL="http://127.0.0.1:8080/v1",
        LLM_API_KEY="test-key",
        LLM_MODEL="test-model",
    )
    return replace(defaults, **cast("Any", overrides))
