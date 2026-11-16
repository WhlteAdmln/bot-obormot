# VENDORED: keep identical in bot-obormot and audiodoc. Source of truth: audiodoc.
# Copyright (c) 2026 Nikolai Zelensky
"""Shared environment-variable readers."""

import math
import os
import warnings
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv


def get_home_dir(environ: Mapping[str, str] | None = None) -> Path:
    """Return the application home directory."""
    source = os.environ if environ is None else environ
    configured_home = source.get("AUDIODOC_HOME", "").strip()
    configured_user_home = source.get("HOME", "").strip()
    user_home = (
        Path(configured_user_home).expanduser() if configured_user_home else Path.home()
    )
    home = (
        Path(configured_home).expanduser()
        if configured_home
        else user_home / "audiodoc"
    )
    return home if home.is_absolute() else Path.cwd() / home


def resolve_home_path(value: str, home: Path) -> Path:
    """Resolve a configured path relative to the application home."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else home / path


def load_env_file(env_file: str | Path | None = None) -> None:
    """Load environment files in precedence order without overriding existing values."""
    loaded_paths: set[Path] = set()

    if env_file is not None:
        explicit_path = Path(env_file).expanduser()
        load_dotenv(explicit_path, override=False)
        loaded_paths.add(explicit_path.resolve())

    dotenv_paths = (get_home_dir() / ".env", Path.cwd() / ".env")
    for dotenv_path in dotenv_paths:
        resolved_path = dotenv_path.resolve()
        if resolved_path in loaded_paths:
            continue
        load_dotenv(dotenv_path, override=False)
        loaded_paths.add(resolved_path)


def get_bool(
    name: str, default: bool = False, *, environ: Mapping[str, str] | None = None
) -> bool:
    """Read a boolean environment variable using common spellings."""
    source = os.environ if environ is None else environ
    value = source.get(name)

    if value is None or not value.strip():
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False

    message = f"Setting {name} must be true or false. Got: {value!r}"
    raise ValueError(message)


def get_int(
    name: str,
    default: str,
    minimum: int = 1,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Read an integer setting and enforce its lower bound."""
    source = os.environ if environ is None else environ
    value = source.get(name, default)

    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        message = f"Setting {name} must be an integer. Got: {value!r}"
        raise ValueError(message) from error

    if result < minimum:
        message = f"Setting {name} must be at least {minimum}."
        message += f" Got: {result}"
        raise ValueError(message)

    return result


def get_optional_int(
    name: str,
    minimum: int = 1,
    *,
    environ: Mapping[str, str] | None = None,
) -> int | None:
    """Read an optional integer setting; an empty value means None."""
    source = os.environ if environ is None else environ
    value = source.get(name)

    if value is None or not value.strip():
        return None

    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        message = f"Setting {name} must be an integer. Got: {value!r}"
        raise ValueError(message) from error

    if result < minimum:
        message = f"Setting {name} must be at least {minimum}."
        message += f" Got: {result}"
        raise ValueError(message)

    return result


def get_float(
    name: str,
    default: str,
    minimum: float | None = None,
    maximum: float | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> float:
    """Read a finite float setting and enforce optional bounds."""
    source = os.environ if environ is None else environ
    value = source.get(name, default)

    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        message = f"Setting {name} must be a number. Got: {value!r}"
        raise ValueError(message) from error

    if not math.isfinite(result):
        message = f"Setting {name} must be a finite number."
        message += f" Got: {value!r}"
        raise ValueError(message)

    if minimum is not None and result < minimum:
        message = f"Setting {name} must be at least {minimum}."
        message += f" Got: {result}"
        raise ValueError(message)

    if maximum is not None and result > maximum:
        message = f"Setting {name} must be at most {maximum}."
        message += f" Got: {result}"
        raise ValueError(message)

    return result


def get_log_level(*, environ: Mapping[str, str] | None = None) -> str:
    """Return a valid logging level, defaulting to INFO for invalid values."""
    source = os.environ if environ is None else environ
    value = source.get("LOG_LEVEL", "INFO").strip().upper()

    allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if value not in allowed_levels:
        warnings.warn(
            f"Invalid LOG_LEVEL={value!r}. Falling back to INFO.",
            RuntimeWarning,
            stacklevel=2,
        )
        return "INFO"

    return value


def parse_ids(name: str, *, environ: Mapping[str, str] | None = None) -> set[int]:
    """Read a comma-separated environment variable containing positive IDs."""
    source = os.environ if environ is None else environ
    value = source.get(name, "").strip()

    if not value:
        return set()

    result: set[int] = set()
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue

        try:
            user_id = int(item)
        except ValueError as error:
            message = f"Setting {name} contains an invalid ID: {item!r}"
            raise ValueError(message) from error

        if user_id <= 0:
            message = f"ID in setting {name} must be positive: {user_id}"
            raise ValueError(message)

        result.add(user_id)

    return result
