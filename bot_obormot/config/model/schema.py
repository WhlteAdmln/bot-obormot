# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""The immutable settings schema with its defaults."""

from dataclasses import dataclass, field

from bot_obormot.config.prompts import load_default_system_prompt

_DEFAULT_COUNTING_MODE = "auto"


# One field per environment variable; splitting them would only hide the schema.
@dataclass(frozen=True, slots=True)
class Settings:  # pylint: disable=too-many-instance-attributes
    """Application settings loaded from environment variables."""

    BOT_TOKEN: str = ""
    LOG_LEVEL: str = "INFO"
    SUPERVISOR_ID: int = 1
    ADMIN_IDS: set[int] = field(default_factory=set)
    ALLOWED_USERS: set[int] = field(default_factory=set)
    ALLOW_ALL_USERS: bool = False
    LLM_BASE_URL: str = "http://127.0.0.1:8080/v1"
    LLM_API_KEY: str = "not-needed"
    LLM_MODEL: str = "local-model"
    LLM_TEMPERATURE: float = 0.7
    LLM_TOP_P: float = 0.9
    LLM_MAX_TOKENS: int = 2048
    LLM_TIMEOUT: int = 300
    LLM_CONTEXT_SIZE: int | None = None
    LLM_TOKEN_COUNTING: str = _DEFAULT_COUNTING_MODE
    LLM_MAX_CONCURRENT_GENERATIONS: int = 1
    DEFAULT_HISTORY_EXCHANGES: int = 30
    MAX_HISTORY_EXCHANGES: int = 1000
    MAX_STORED_EXCHANGES: int = 2000
    DATABASE_PATH: str = "data/bot.db"
    SYSTEM_PROMPT_PATH: str = ""
    DEFAULT_SYSTEM_PROMPT: str = field(default_factory=load_default_system_prompt)
    AUDIODOC_URL: str = ""
    AUDIODOC_AUDIO_KEY: str = ""
    AUDIODOC_DOCUMENT_KEY: str = ""
    AUDIODOC_AUDIO_TIMEOUT: int = 180
    AUDIODOC_DOCUMENT_TIMEOUT: int = 300
