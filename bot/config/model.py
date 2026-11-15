# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Immutable application settings and their compatibility interface."""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache

from bot.config.env import (
    get_bool,
    get_float,
    get_int,
    get_log_level,
    get_optional_int,
    parse_ids,
)
from bot.config.prompts import load_default_system_prompt


class ConfigError(ValueError):
    """Raised when one or more environment settings are invalid."""

    def __init__(self, errors: list[str]) -> None:
        """Initialize the error with every invalid setting."""
        self.errors = tuple(errors)
        super().__init__("Invalid configuration:\n" + "\n".join(errors))


_DEFAULT_COUNTING_MODE = "auto"


@dataclass(frozen=True, slots=True)
class Settings:
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
    DEFAULT_SYSTEM_PROMPT: str = field(default_factory=load_default_system_prompt)
    WHISPER_API_URL: str = ""
    WHISPER_API_KEY: str = ""
    WHISPER_TIMEOUT: int = 180
    DOCUMENT_API_URL: str = ""
    DOCUMENT_API_KEY: str = ""
    DOCUMENT_TIMEOUT: int = 300


class _SettingsLoader:
    """Read validated settings from one environment mapping."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        self.environ = environ
        self.errors: list[str] = []
        self.defaults = Settings()

    def _read_str(
        self,
        name: str,
        default: str,
        *,
        strip: bool = False,
        lower: bool = False,
    ) -> str:
        value = self.environ.get(name, default)
        if strip:
            value = value.strip()
        return value.lower() if lower else value

    def _read_bool(self, name: str, *, default: bool) -> bool:
        try:
            return get_bool(
                name,
                default=default,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return default

    def _read_int(
        self,
        name: str,
        default: int,
        *,
        minimum: int = 1,
        required: bool = False,
    ) -> int:
        raw_default = "" if required else str(default)
        try:
            return get_int(
                name,
                raw_default,
                minimum,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return default

    def _read_optional_int(self, name: str) -> int | None:
        try:
            return get_optional_int(
                name,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return None

    def _read_float(
        self,
        name: str,
        default: float,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        try:
            return get_float(
                name,
                str(default),
                minimum=minimum,
                maximum=maximum,
                environ=self.environ,
            )
        except ValueError as error:
            self.errors.append(str(error))
            return default

    def _read_ids(self, name: str) -> set[int]:
        try:
            return parse_ids(name, environ=self.environ)
        except ValueError as error:
            self.errors.append(str(error))
            return set()

    def _read_token_counting(self) -> str:
        value = self._read_str(
            "LLM_TOKEN_COUNTING",
            self.defaults.LLM_TOKEN_COUNTING,
            strip=True,
            lower=True,
        )

        if value not in {"auto", "llamacpp", "estimate"}:
            self.errors.append("LLM_TOKEN_COUNTING must be auto, llamacpp, or estimate")
            return self.defaults.LLM_TOKEN_COUNTING

        return value

    def _read_database_path(self) -> str:
        value = self._read_str(
            "DATABASE_PATH",
            self.defaults.DATABASE_PATH,
            strip=True,
        )

        if not value:
            self.errors.append("DATABASE_PATH must not be empty")
            return self.defaults.DATABASE_PATH

        return value

    def load(self) -> Settings:
        """Build settings and raise one error containing all invalid values."""
        defaults = self.defaults

        result = Settings(
            BOT_TOKEN=self._read_str(
                "BOT_TOKEN",
                defaults.BOT_TOKEN,
                strip=True,
            ),
            LOG_LEVEL=get_log_level(environ=self.environ),
            SUPERVISOR_ID=self._read_int(
                "SUPERVISOR_ID",
                defaults.SUPERVISOR_ID,
                required=True,
            ),
            ADMIN_IDS=self._read_ids("ADMIN_IDS"),
            ALLOWED_USERS=self._read_ids("ALLOWED_USERS"),
            ALLOW_ALL_USERS=self._read_bool(
                "ALLOW_ALL_USERS",
                default=defaults.ALLOW_ALL_USERS,
            ),
            LLM_BASE_URL=self._read_str(
                "LLM_BASE_URL",
                defaults.LLM_BASE_URL,
            ).rstrip("/"),
            LLM_API_KEY=self._read_str(
                "LLM_API_KEY",
                defaults.LLM_API_KEY,
            ),
            LLM_MODEL=self._read_str(
                "LLM_MODEL",
                defaults.LLM_MODEL,
            ),
            LLM_TEMPERATURE=self._read_float(
                "LLM_TEMPERATURE",
                defaults.LLM_TEMPERATURE,
                minimum=0.0,
            ),
            LLM_TOP_P=self._read_float(
                "LLM_TOP_P",
                defaults.LLM_TOP_P,
                minimum=0.0,
                maximum=1.0,
            ),
            LLM_MAX_TOKENS=self._read_int(
                "LLM_MAX_TOKENS",
                defaults.LLM_MAX_TOKENS,
            ),
            LLM_TIMEOUT=self._read_int(
                "LLM_TIMEOUT",
                defaults.LLM_TIMEOUT,
            ),
            LLM_CONTEXT_SIZE=self._read_optional_int("LLM_CONTEXT_SIZE"),
            LLM_TOKEN_COUNTING=self._read_token_counting(),
            LLM_MAX_CONCURRENT_GENERATIONS=self._read_int(
                "LLM_MAX_CONCURRENT_GENERATIONS",
                defaults.LLM_MAX_CONCURRENT_GENERATIONS,
            ),
            DEFAULT_HISTORY_EXCHANGES=defaults.DEFAULT_HISTORY_EXCHANGES,
            MAX_HISTORY_EXCHANGES=self._read_int(
                "MAX_HISTORY_EXCHANGES",
                defaults.MAX_HISTORY_EXCHANGES,
            ),
            MAX_STORED_EXCHANGES=self._read_int(
                "MAX_STORED_EXCHANGES",
                defaults.MAX_STORED_EXCHANGES,
            ),
            DATABASE_PATH=self._read_database_path(),
            DEFAULT_SYSTEM_PROMPT=defaults.DEFAULT_SYSTEM_PROMPT,
            WHISPER_API_URL=self._read_str(
                "WHISPER_API_URL",
                defaults.WHISPER_API_URL,
            ).rstrip("/"),
            WHISPER_API_KEY=self._read_str(
                "WHISPER_API_KEY",
                defaults.WHISPER_API_KEY,
                strip=True,
            ),
            WHISPER_TIMEOUT=self._read_int(
                "WHISPER_TIMEOUT",
                defaults.WHISPER_TIMEOUT,
            ),
            DOCUMENT_API_URL=self._read_str(
                "DOCUMENT_API_URL",
                defaults.DOCUMENT_API_URL,
                strip=True,
            ).rstrip("/"),
            DOCUMENT_API_KEY=self._read_str(
                "DOCUMENT_API_KEY",
                defaults.DOCUMENT_API_KEY,
                strip=True,
            ),
            DOCUMENT_TIMEOUT=self._read_int(
                "DOCUMENT_TIMEOUT",
                defaults.DOCUMENT_TIMEOUT,
            ),
        )

        if self.errors:
            raise ConfigError(self.errors)

        return result


def load_settings(environ: Mapping[str, str]) -> Settings:
    """Build settings from an environment mapping and collect validation errors."""
    return _SettingsLoader(environ).load()


@lru_cache(maxsize=1)
def _load_cached_settings() -> Settings:
    return load_settings(os.environ)


def get_settings() -> Settings:
    """Return the process-wide cached settings."""
    return _load_cached_settings()


def reset_settings_cache() -> None:
    """Clear cached settings."""
    _load_cached_settings.cache_clear()
