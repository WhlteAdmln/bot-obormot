# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Build validated settings from an environment mapping."""

from collections.abc import Mapping
from pathlib import Path

from bot_obormot.config.model.readers import EnvironmentReader
from bot_obormot.config.model.schema import Settings
from bot_obormot.config.prompts import load_system_prompt_file
from bot_obormot.env_readers import get_home_dir, get_log_level, resolve_home_path


class ConfigError(ValueError):
    """Raised when one or more environment settings are invalid."""

    def __init__(self, errors: list[str]) -> None:
        """Initialize the error with every invalid setting."""
        self.errors = tuple(errors)
        super().__init__("Invalid configuration:\n" + "\n".join(errors))


class _SettingsLoader:
    """Read validated settings from one environment mapping."""

    def __init__(self, environ: Mapping[str, str]) -> None:
        self.reader = EnvironmentReader(environ)
        self.defaults = Settings()

    def _read_token_counting(self) -> str:
        value = self.reader.read_str(
            "LLM_TOKEN_COUNTING",
            self.defaults.LLM_TOKEN_COUNTING,
            strip=True,
            lower=True,
        )

        if value not in {"auto", "llamacpp", "estimate"}:
            self.reader.errors.append(
                "LLM_TOKEN_COUNTING must be auto, llamacpp, or estimate"
            )
            return self.defaults.LLM_TOKEN_COUNTING

        return value

    def _read_database_path(self) -> str:
        value = self.reader.read_str(
            "DATABASE_PATH",
            self.defaults.DATABASE_PATH,
            strip=True,
        )

        if not value:
            self.reader.errors.append("DATABASE_PATH must not be empty")
            return self.defaults.DATABASE_PATH

        # Relative paths resolve against the application home directory.
        return str(resolve_home_path(value, get_home_dir(self.reader.environ)))

    def _read_system_prompt_path(self) -> str:
        value = self.reader.read_str(
            "SYSTEM_PROMPT_PATH",
            self.defaults.SYSTEM_PROMPT_PATH,
            strip=True,
        )

        if not value:
            return ""

        # Relative paths resolve against the application home directory.
        return str(resolve_home_path(value, get_home_dir(self.reader.environ)))

    def _read_system_prompt(self, path: str) -> str:
        if not path:
            return self.defaults.DEFAULT_SYSTEM_PROMPT

        try:
            return load_system_prompt_file(Path(path))
        except ValueError as error:
            self.reader.errors.append(f"SYSTEM_PROMPT_PATH: {error}")
            return self.defaults.DEFAULT_SYSTEM_PROMPT

    def load(self) -> Settings:
        """Build settings and raise one error containing all invalid values."""
        defaults = self.defaults
        system_prompt_path = self._read_system_prompt_path()

        result = Settings(
            BOT_TOKEN=self.reader.read_str(
                "BOT_TOKEN",
                defaults.BOT_TOKEN,
                strip=True,
            ),
            LOG_LEVEL=get_log_level(environ=self.reader.environ),
            SUPERVISOR_ID=self.reader.read_int(
                "SUPERVISOR_ID",
                defaults.SUPERVISOR_ID,
                required=True,
            ),
            ADMIN_IDS=self.reader.read_ids("ADMIN_IDS"),
            ALLOWED_USERS=self.reader.read_ids("ALLOWED_USERS"),
            ALLOW_ALL_USERS=self.reader.read_bool(
                "ALLOW_ALL_USERS",
                default=defaults.ALLOW_ALL_USERS,
            ),
            LLM_BASE_URL=self.reader.read_str(
                "LLM_BASE_URL",
                defaults.LLM_BASE_URL,
            ).rstrip("/"),
            LLM_API_KEY=self.reader.read_str(
                "LLM_API_KEY",
                defaults.LLM_API_KEY,
            ),
            LLM_MODEL=self.reader.read_str(
                "LLM_MODEL",
                defaults.LLM_MODEL,
            ),
            LLM_TEMPERATURE=self.reader.read_float(
                "LLM_TEMPERATURE",
                defaults.LLM_TEMPERATURE,
                minimum=0.0,
            ),
            LLM_TOP_P=self.reader.read_float(
                "LLM_TOP_P",
                defaults.LLM_TOP_P,
                minimum=0.0,
                maximum=1.0,
            ),
            LLM_MAX_TOKENS=self.reader.read_int(
                "LLM_MAX_TOKENS",
                defaults.LLM_MAX_TOKENS,
            ),
            LLM_TIMEOUT=self.reader.read_int(
                "LLM_TIMEOUT",
                defaults.LLM_TIMEOUT,
            ),
            LLM_CONTEXT_SIZE=self.reader.read_optional_int("LLM_CONTEXT_SIZE"),
            LLM_TOKEN_COUNTING=self._read_token_counting(),
            LLM_MAX_CONCURRENT_GENERATIONS=self.reader.read_int(
                "LLM_MAX_CONCURRENT_GENERATIONS",
                defaults.LLM_MAX_CONCURRENT_GENERATIONS,
            ),
            DEFAULT_HISTORY_EXCHANGES=defaults.DEFAULT_HISTORY_EXCHANGES,
            MAX_HISTORY_EXCHANGES=self.reader.read_int(
                "MAX_HISTORY_EXCHANGES",
                defaults.MAX_HISTORY_EXCHANGES,
            ),
            MAX_STORED_EXCHANGES=self.reader.read_int(
                "MAX_STORED_EXCHANGES",
                defaults.MAX_STORED_EXCHANGES,
            ),
            DATABASE_PATH=self._read_database_path(),
            SYSTEM_PROMPT_PATH=system_prompt_path,
            DEFAULT_SYSTEM_PROMPT=self._read_system_prompt(system_prompt_path),
            AUDIODOC_URL=self.reader.read_str(
                "AUDIODOC_URL",
                defaults.AUDIODOC_URL,
                strip=True,
            ).rstrip("/"),
            AUDIODOC_AUDIO_KEY=self.reader.read_str(
                "AUDIODOC_AUDIO_KEY",
                defaults.AUDIODOC_AUDIO_KEY,
                strip=True,
            ),
            AUDIODOC_DOCUMENT_KEY=self.reader.read_str(
                "AUDIODOC_DOCUMENT_KEY",
                defaults.AUDIODOC_DOCUMENT_KEY,
                strip=True,
            ),
            AUDIODOC_AUDIO_TIMEOUT=self.reader.read_int(
                "AUDIODOC_AUDIO_TIMEOUT",
                defaults.AUDIODOC_AUDIO_TIMEOUT,
            ),
            AUDIODOC_DOCUMENT_TIMEOUT=self.reader.read_int(
                "AUDIODOC_DOCUMENT_TIMEOUT",
                defaults.AUDIODOC_DOCUMENT_TIMEOUT,
            ),
        )

        if self.reader.errors:
            raise ConfigError(self.reader.errors)

        return result


def load_settings(environ: Mapping[str, str]) -> Settings:
    """Build settings from an environment mapping and collect validation errors."""
    return _SettingsLoader(environ).load()
