# Copyright (c) 2026 Nikolai Zelensky
"""Check that every setting is in `.env.example` and the configuration guide."""

from __future__ import annotations

import re
from dataclasses import fields
from typing import TYPE_CHECKING

from bot_obormot.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path

# Settings fields that are computed defaults and not environment variables.
_NON_ENVIRONMENT_FIELDS = frozenset(
    {"DEFAULT_HISTORY_EXCHANGES", "DEFAULT_SYSTEM_PROMPT"}
)

# Names documented in docs/configuration.md that are not Settings fields.
DOCUMENTATION_ONLY_ENV_NAMES = frozenset(
    {
        "BOT_OBORMOT_HOME",
    }
)

_ENV_ASSIGNMENT_LINE_RE = re.compile(r"(?m)^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=")
_CONFIG_SETTING_RE = re.compile(r"(?m)^\s*\|\s*`([A-Z][A-Z0-9_]*)`")


def settings_environment_names() -> set[str]:
    """Return environment names corresponding to public Settings fields."""
    return {
        item.name
        for item in fields(Settings)
        if not item.name.startswith("_") and item.name not in _NON_ENVIRONMENT_FIELDS
    }


def check_settings(root: Path) -> list[str]:
    """Check settings correspondence with the environment example and guide."""
    errors: list[str] = []
    example_path = root / ".env.example"
    docs_path = root / "docs" / "configuration.md"

    if not example_path.is_file():
        errors.append(".env.example: file not found")
    if not docs_path.is_file():
        errors.append("docs/configuration.md: file not found")
    if errors:
        return errors

    settings_names = settings_environment_names()
    example_names = set(
        _ENV_ASSIGNMENT_LINE_RE.findall(example_path.read_text(encoding="utf-8"))
    )
    docs_names = set(_CONFIG_SETTING_RE.findall(docs_path.read_text(encoding="utf-8")))

    missing_example = sorted(settings_names - example_names)
    extra_example = sorted(example_names - settings_names)

    if missing_example:
        errors.append(
            ".env.example: missing Settings fields: " + ", ".join(missing_example)
        )
    if extra_example:
        errors.append(".env.example: unknown settings: " + ", ".join(extra_example))

    expected_docs = settings_names | DOCUMENTATION_ONLY_ENV_NAMES
    missing_docs = sorted(expected_docs - docs_names)
    extra_docs = sorted(docs_names - expected_docs)

    if missing_docs:
        errors.append(
            "docs/configuration.md: missing settings: " + ", ".join(missing_docs)
        )
    if extra_docs:
        errors.append(
            "docs/configuration.md: unknown settings: " + ", ".join(extra_docs)
        )

    return errors
