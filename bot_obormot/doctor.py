# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Installation diagnostics: every check is a small function with a result object."""

import os
import shutil
import stat
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from bot_obormot.config.token import is_valid_bot_token
from bot_obormot.env_readers import get_home_dir
from bot_obormot.services.media.animation.tgs import tgs_support_available
from bot_obormot.settings import ConfigError, Settings, load_settings

CheckStatus = Literal["OK", "WARN", "FAIL"]

MIN_PYTHON = (3, 11)
HTTP_TIMEOUT_SECONDS = 3.0
HTTP_OK_LIMIT = 400
PRIVATE_MODE_MASK = 0o077
PLACEHOLDER_PREFIXES = ("YOUR_", "REPLACE_WITH")
_SKIPPED_OFFLINE = "Skipped (--offline)."
_SKIPPED_INVALID = "Skipped because the configuration is invalid."


@dataclass(frozen=True, slots=True)
class DiagnosticCheck:
    """Describe the result of one diagnostic check."""

    name: str
    status: CheckStatus
    message: str


def check_python_version() -> DiagnosticCheck:
    """Check that the running Python version is supported."""
    major, minor = sys.version_info[:2]
    if (major, minor) < MIN_PYTHON:
        return DiagnosticCheck(
            "Python",
            "FAIL",
            f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer is required; "
            f"found {major}.{minor}.",
        )
    return DiagnosticCheck("Python", "OK", f"Python {major}.{minor} is supported.")


def check_env_file(environ: Mapping[str, str]) -> DiagnosticCheck:
    """Check that the .env file exists and is private.

    A missing file is only a warning because Docker and systemd can provide
    the settings through the process environment.
    """
    env_path = get_home_dir(environ) / ".env"
    try:
        metadata = env_path.lstat()
    except FileNotFoundError:
        return DiagnosticCheck(
            "Environment file",
            "WARN",
            f"Not found: {env_path}. Using the process environment only. "
            "Run 'bot-obormot init' to create it.",
        )
    except OSError as error:
        return DiagnosticCheck(
            "Environment file", "FAIL", f"Cannot inspect {env_path}: {error}."
        )

    if not stat.S_ISREG(metadata.st_mode):
        return DiagnosticCheck(
            "Environment file", "FAIL", f"{env_path} is not a regular file."
        )
    if metadata.st_mode & PRIVATE_MODE_MASK:
        mode = stat.S_IMODE(metadata.st_mode)
        return DiagnosticCheck(
            "Environment file",
            "WARN",
            f"{env_path} is readable by other users (mode {mode:03o}); "
            f"run: chmod 600 {env_path}",
        )
    return DiagnosticCheck("Environment file", "OK", f"Found {env_path} (mode 600).")


def check_settings(
    environ: Mapping[str, str],
) -> tuple[DiagnosticCheck, Settings | None]:
    """Load the settings and report every problem without printing secrets."""
    try:
        settings = load_settings(environ)
    except ConfigError as error:
        problems = [message.partition(" Got:")[0] for message in error.errors]
        return (
            DiagnosticCheck(
                "Settings",
                "FAIL",
                f"{len(problems)} problem(s): " + "; ".join(problems),
            ),
            None,
        )
    return DiagnosticCheck("Settings", "OK", "All settings are valid."), settings


def check_bot_token(environ: Mapping[str, str]) -> DiagnosticCheck:
    """Check the Telegram token format without printing it."""
    token = environ.get("BOT_TOKEN", "").strip()
    if not token:
        return DiagnosticCheck("Telegram token", "FAIL", "BOT_TOKEN is not set.")
    if token.startswith(PLACEHOLDER_PREFIXES):
        return DiagnosticCheck(
            "Telegram token", "FAIL", "BOT_TOKEN still contains the template value."
        )
    if not is_valid_bot_token(token):
        return DiagnosticCheck(
            "Telegram token", "FAIL", "BOT_TOKEN has an invalid format."
        )
    return DiagnosticCheck("Telegram token", "OK", "BOT_TOKEN has a valid format.")


def check_ffmpeg() -> DiagnosticCheck:
    """Check that ffmpeg and ffprobe are available for video processing."""
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        return DiagnosticCheck(
            "ffmpeg",
            "WARN",
            f"Missing: {', '.join(missing)}. Video and animation are unavailable.",
        )
    return DiagnosticCheck("ffmpeg", "OK", "ffmpeg and ffprobe are available.")


def check_tgs_support() -> DiagnosticCheck:
    """Report whether the optional animated-sticker decoder is installed."""
    if tgs_support_available():
        return DiagnosticCheck(
            "Animated stickers", "OK", "rlottie-python is installed."
        )
    return DiagnosticCheck(
        "Animated stickers",
        "WARN",
        'Disabled. Install the optional extra: pip install "bot-obormot[tgs]" '
        "(needs a C compiler and CMake).",
    )


def _nearest_existing_parent(path: Path) -> Path:
    """Return the closest existing ancestor of a path."""
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def check_database_path(settings: Settings) -> DiagnosticCheck:
    """Check that the SQLite database can be created or written."""
    database_path = Path(settings.DATABASE_PATH)
    if database_path.exists():
        writable = os.access(database_path, os.W_OK)
        target = database_path
    else:
        target = _nearest_existing_parent(database_path.parent)
        writable = os.access(target, os.W_OK | os.X_OK)
    if not writable:
        return DiagnosticCheck(
            "Database", "FAIL", f"{target} is not writable (DATABASE_PATH)."
        )
    return DiagnosticCheck(
        "Database", "OK", f"Database path is writable: {database_path}."
    )


def _display_url(url: str) -> str:
    """Return scheme, host and port only, so credentials never reach the output."""
    parts = urlsplit(url)
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{parts.hostname}{port}"


def fetch_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
    """Return the HTTP status of a GET request; raise OSError when unreachable."""
    if urlsplit(url).scheme not in {"http", "https"}:
        message = "Only http and https URLs are supported."
        raise ValueError(message)
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)
    except urllib.error.URLError as error:
        message = str(error.reason)
        raise OSError(message) from error


def _check_http(
    name: str,
    url: str,
    headers: Mapping[str, str],
    *,
    failure: CheckStatus,
) -> DiagnosticCheck:
    """Run one reachability probe and map failures to the requested status."""
    shown = _display_url(url)
    try:
        status = fetch_status(url, headers, HTTP_TIMEOUT_SECONDS)
    except (OSError, ValueError) as error:
        return DiagnosticCheck(name, failure, f"{shown} is unreachable: {error}.")
    if status >= HTTP_OK_LIMIT:
        return DiagnosticCheck(name, failure, f"{shown} returned HTTP {status}.")
    return DiagnosticCheck(name, "OK", f"{shown} is reachable (HTTP {status}).")


def check_llm_server(settings: Settings, *, offline: bool) -> DiagnosticCheck:
    """Check that the OpenAI-compatible server answers on /models."""
    if offline:
        return DiagnosticCheck("LLM server", "OK", _SKIPPED_OFFLINE)
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
    return _check_http(
        "LLM server",
        f"{settings.LLM_BASE_URL}/models",
        headers,
        failure="FAIL",
    )


def check_audiodoc(settings: Settings, *, offline: bool) -> DiagnosticCheck:
    """Check that the optional audiodoc service answers on /health."""
    if not settings.AUDIODOC_URL:
        return DiagnosticCheck(
            "audiodoc",
            "OK",
            "Not configured; audio and document processing are disabled.",
        )
    if offline:
        return DiagnosticCheck("audiodoc", "OK", _SKIPPED_OFFLINE)
    return _check_http(
        "audiodoc", f"{settings.AUDIODOC_URL}/health", {}, failure="WARN"
    )


def collect_doctor_checks(
    environ: Mapping[str, str],
    *,
    offline: bool = False,
) -> list[DiagnosticCheck]:
    """Run all diagnostics and return their results in display order."""
    settings_check, settings = check_settings(environ)
    checks = [
        check_python_version(),
        check_env_file(environ),
        settings_check,
        check_bot_token(environ),
        check_ffmpeg(),
        check_tgs_support(),
    ]
    if settings is None:
        checks.extend(
            DiagnosticCheck(name, "WARN", _SKIPPED_INVALID)
            for name in ("Database", "LLM server", "audiodoc")
        )
        return checks

    checks.extend(
        (
            check_database_path(settings),
            check_llm_server(settings, offline=offline),
            check_audiodoc(settings, offline=offline),
        )
    )
    return checks
