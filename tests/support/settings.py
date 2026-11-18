# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Factories for isolated application settings in tests."""

from dataclasses import replace
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from bot_obormot.settings import Settings

_LEGACY_SETTING_NAMES = {
    "WHISPER_API_KEY": "AUDIODOC_AUDIO_KEY",
    "DOCUMENT_API_KEY": "AUDIODOC_DOCUMENT_KEY",
    "WHISPER_TIMEOUT": "AUDIODOC_AUDIO_TIMEOUT",
    "DOCUMENT_TIMEOUT": "AUDIODOC_DOCUMENT_TIMEOUT",
}


def _legacy_base_url(value: str, endpoint: str) -> str:
    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    suffix = f"/{endpoint}"
    path = path.removesuffix(suffix)
    return urlunsplit(
        (parts.scheme, parts.netloc, path, parts.query, parts.fragment)
    ).rstrip("/")


def make_settings(**overrides: object) -> Settings:
    """Build test settings with optional field overrides."""
    normalized = dict(overrides)
    audio_url = normalized.pop("WHISPER_API_URL", None)
    document_url = normalized.pop("DOCUMENT_API_URL", None)

    if "AUDIODOC_URL" not in normalized:
        if audio_url is not None and str(audio_url).strip():
            normalized["AUDIODOC_URL"] = _legacy_base_url(str(audio_url), "transcribe")
        elif document_url is not None and str(document_url).strip():
            normalized["AUDIODOC_URL"] = _legacy_base_url(
                str(document_url), "process-document"
            )
        elif audio_url is not None or document_url is not None:
            normalized["AUDIODOC_URL"] = ""

    for legacy_name, new_name in _LEGACY_SETTING_NAMES.items():
        if legacy_name in normalized:
            value = normalized.pop(legacy_name)
            normalized.setdefault(new_name, value)

    defaults = Settings(
        BOT_TOKEN="123456789:" + "A" * 35,
        LOG_LEVEL="WARNING",
        SUPERVISOR_ID=999999999,
        DATABASE_PATH="data/test-bot.db",
        LLM_BASE_URL="http://127.0.0.1:8080/v1",
        LLM_API_KEY="test-key",
        LLM_MODEL="test-model",
    )
    return replace(defaults, **cast("Any", normalized))
