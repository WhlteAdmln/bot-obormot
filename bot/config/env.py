# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Helpers that read and validate settings from environment variables."""

import math
import os
import warnings
from collections.abc import Mapping

from dotenv import load_dotenv

from bot.config.paths import PROJECT_ROOT


def _get_environment(environ: Mapping[str, str] | None) -> Mapping[str, str]:
    return os.environ if environ is None else environ


def get_bool(
    name: str,
    *,
    default: bool = False,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Read a boolean environment variable."""
    value = _get_environment(environ).get(name)

    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()

    if normalized in {"1", "true", "yes", "on"}:
        return True

    if normalized in {"0", "false", "no", "off"}:
        return False

    msg = f"Setting {name} must be true or false. Got: {value!r}"
    raise ValueError(msg)


def get_int(
    name: str,
    default: str,
    minimum: int = 1,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Read an integer environment variable and check its lower bound."""
    value = _get_environment(environ).get(name, default)

    try:
        result = int(value)
    except (TypeError, ValueError) as err:
        msg = f"Setting {name} must be an integer. Got: {value!r}"
        raise ValueError(msg) from err

    if result < minimum:
        msg = f"Setting {name} must be at least {minimum}. Got: {result}"
        raise ValueError(msg)

    return result


def get_optional_int(
    name: str,
    minimum: int = 1,
    *,
    environ: Mapping[str, str] | None = None,
) -> int | None:
    """Read an optional integer environment variable."""
    value = _get_environment(environ).get(name)

    if value is None or not value.strip():
        return None

    try:
        result = int(value)
    except (TypeError, ValueError) as err:
        msg = f"Setting {name} must be an integer. Got: {value!r}"
        raise ValueError(msg) from err

    if result < minimum:
        msg = f"Setting {name} must be at least {minimum}. Got: {result}"
        raise ValueError(msg)

    return result


def get_float(
    name: str,
    default: str,
    minimum: float | None = None,
    maximum: float | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> float:
    """Read a finite float environment variable and check its bounds."""
    value = _get_environment(environ).get(name, default)

    try:
        result = float(value)
    except (TypeError, ValueError) as err:
        msg = f"Setting {name} must be a number. Got: {value!r}"
        raise ValueError(msg) from err

    if not math.isfinite(result):
        msg = f"Setting {name} must be finite. Got: {value!r}"
        raise ValueError(msg)

    if minimum is not None and result < minimum:
        msg = f"Setting {name} must be at least {minimum}. Got: {result}"
        raise ValueError(msg)

    if maximum is not None and result > maximum:
        msg = f"Setting {name} must be at most {maximum}. Got: {result}"
        raise ValueError(msg)

    return result


def get_log_level(*, environ: Mapping[str, str] | None = None) -> str:
    """Return a valid logging level."""
    value = _get_environment(environ).get("LOG_LEVEL", "INFO").strip().upper()

    allowed_levels = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    if value not in allowed_levels:
        warnings.warn(
            f"Invalid LOG_LEVEL={value!r}. Using INFO.",
            RuntimeWarning,
            stacklevel=2,
        )
        return "INFO"

    return value


def parse_ids(name: str, *, environ: Mapping[str, str] | None = None) -> set[int]:
    """Parse a comma-separated environment variable into positive integer IDs."""
    value = _get_environment(environ).get(name, "").strip()

    if not value:
        return set()

    result: set[int] = set()

    for raw_item in value.split(","):
        item = raw_item.strip()

        if not item:
            continue

        try:
            user_id = int(item)
        except ValueError as err:
            msg = f"Setting {name} contains an invalid ID: {item!r}"
            raise ValueError(msg) from err

        if user_id <= 0:
            msg = f"IDs in setting {name} must be positive. Got: {user_id}"
            raise ValueError(msg)

        result.add(user_id)

    return result


def load_env_file() -> None:
    """Load the project .env file into the process environment."""
    load_dotenv(PROJECT_ROOT / ".env")
