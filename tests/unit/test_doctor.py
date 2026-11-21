# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the installation diagnostics; every check has success and failure."""

import io
import sys
import urllib.error
from collections.abc import Mapping
from email.message import Message
from pathlib import Path

import pytest

from bot_obormot import doctor
from bot_obormot.settings import Settings

VALID_TOKEN = "123456789:" + "A" * 35


def _environ(tmp_path: Path, **overrides: str) -> dict[str, str]:
    """Build a valid environment rooted in a temporary home."""
    values = {
        "BOT_OBORMOT_HOME": str(tmp_path),
        "HOME": str(tmp_path),
        "BOT_TOKEN": VALID_TOKEN,
        "SUPERVISOR_ID": "42",
    }
    values.update(overrides)
    return values


def test_python_version_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Supported Python passes; an old interpreter fails."""
    assert doctor.check_python_version().status == "OK"

    monkeypatch.setattr(sys, "version_info", (3, 10, 0, "final", 0))
    result = doctor.check_python_version()

    assert result.status == "FAIL"
    assert "3.11" in result.message


def test_env_file_ok_with_private_permissions(tmp_path: Path) -> None:
    """A private .env file passes."""
    env_path = tmp_path / ".env"
    env_path.write_text("A=1\n", encoding="utf-8")
    env_path.chmod(0o600)

    assert doctor.check_env_file(_environ(tmp_path)).status == "OK"


def test_env_file_warns_when_open_or_missing(tmp_path: Path) -> None:
    """Open permissions and a missing file are warnings, not failures."""
    missing = doctor.check_env_file(_environ(tmp_path))
    assert missing.status == "WARN"
    assert "process environment" in missing.message

    env_path = tmp_path / ".env"
    env_path.write_text("A=1\n", encoding="utf-8")
    env_path.chmod(0o644)
    opened = doctor.check_env_file(_environ(tmp_path))
    assert opened.status == "WARN"
    assert "chmod 600" in opened.message


def test_env_file_fails_for_a_directory(tmp_path: Path) -> None:
    """A directory in place of the file is a failure."""
    (tmp_path / ".env").mkdir()

    assert doctor.check_env_file(_environ(tmp_path)).status == "FAIL"


def test_settings_success_and_failure_without_secrets(tmp_path: Path) -> None:
    """Invalid settings are listed by name and values are not echoed."""
    ok_check, settings = doctor.check_settings(_environ(tmp_path))
    assert ok_check.status == "OK"
    assert settings is not None

    bad_check, bad_settings = doctor.check_settings(
        _environ(tmp_path, SUPERVISOR_ID="secret-value", LLM_TIMEOUT="0")
    )
    assert bad_check.status == "FAIL"
    assert bad_settings is None
    assert "SUPERVISOR_ID" in bad_check.message
    assert "LLM_TIMEOUT" in bad_check.message
    assert "secret-value" not in bad_check.message


@pytest.mark.parametrize(
    ("token", "status"),
    [
        (VALID_TOKEN, "OK"),
        ("", "FAIL"),
        ("YOUR_TELEGRAM_BOT_TOKEN", "FAIL"),
        ("not-a-token", "FAIL"),
    ],
)
def test_bot_token_format(token: str, status: str) -> None:
    """The token is accepted only in the Telegram format."""
    result = doctor.check_bot_token({"BOT_TOKEN": token})

    assert result.status == status
    if token:
        assert token not in result.message


def test_ffmpeg_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Missing ffmpeg tools produce a warning that names them."""
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert doctor.check_ffmpeg().status == "OK"

    monkeypatch.setattr(
        doctor.shutil, "which", lambda name: None if name == "ffprobe" else "/bin/x"
    )
    result = doctor.check_ffmpeg()
    assert result.status == "WARN"
    assert "ffprobe" in result.message
    assert "ffmpeg," not in result.message


def test_tgs_support_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The optional extra is reported as a warning when it is absent."""
    monkeypatch.setattr(doctor, "tgs_support_available", lambda: True)
    assert doctor.check_tgs_support().status == "OK"

    monkeypatch.setattr(doctor, "tgs_support_available", lambda: False)
    result = doctor.check_tgs_support()
    assert result.status == "WARN"
    assert "bot-obormot[tgs]" in result.message


def test_database_path_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A creatable path passes; an unwritable ancestor fails."""
    good = Settings(DATABASE_PATH=str(tmp_path / "new" / "data" / "bot.db"))
    assert doctor.check_database_path(good).status == "OK"

    existing = tmp_path / "bot.db"
    existing.write_text("", encoding="utf-8")
    existing_settings = Settings(DATABASE_PATH=str(existing))
    assert doctor.check_database_path(existing_settings).status == "OK"

    monkeypatch.setattr(doctor.os, "access", lambda _path, _mode: False)
    result = doctor.check_database_path(good)
    assert result.status == "FAIL"
    assert "DATABASE_PATH" in result.message


def test_llm_server_success_failure_and_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LLM probe uses /models with the key and is skipped offline."""
    calls: list[tuple[str, Mapping[str, str]]] = []

    def fake_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
        _ = timeout
        calls.append((url, headers))
        return 200

    monkeypatch.setattr(doctor, "fetch_status", fake_status)
    settings = Settings(LLM_BASE_URL="http://llm.test:8080/v1", LLM_API_KEY="k")

    assert doctor.check_llm_server(settings, offline=False).status == "OK"
    assert calls == [("http://llm.test:8080/v1/models", {"Authorization": "Bearer k"})]

    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 503)
    assert doctor.check_llm_server(settings, offline=False).status == "FAIL"

    def unreachable(*_args: object) -> int:
        message = "connection refused"
        raise OSError(message)

    monkeypatch.setattr(doctor, "fetch_status", unreachable)
    failed = doctor.check_llm_server(settings, offline=False)
    assert failed.status == "FAIL"
    assert "Bearer" not in failed.message

    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: pytest.fail("network"))
    skipped = doctor.check_llm_server(settings, offline=True)
    assert skipped.status == "OK"
    assert "offline" in skipped.message


def test_audiodoc_success_failure_unconfigured_and_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """audiodoc is optional: unreachable is a warning, unset is fine."""
    seen: list[str] = []

    def fake_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
        _ = headers, timeout
        seen.append(url)
        return 200

    monkeypatch.setattr(doctor, "fetch_status", fake_status)
    configured = Settings(AUDIODOC_URL="http://user:pw@audio.test:8000")

    result = doctor.check_audiodoc(configured, offline=False)
    assert result.status == "OK"
    assert seen == ["http://user:pw@audio.test:8000/health"]
    assert "pw" not in result.message

    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 500)
    assert doctor.check_audiodoc(configured, offline=False).status == "WARN"

    assert doctor.check_audiodoc(Settings(), offline=False).status == "OK"
    assert doctor.check_audiodoc(configured, offline=True).status == "OK"


def test_fetch_status_rejects_other_schemes_and_maps_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only http(s) is allowed; URL errors become OSError, HTTP errors a status."""
    with pytest.raises(ValueError, match="http"):
        doctor.fetch_status("file:///etc/passwd", {}, 1.0)

    def raise_http(*_args: object, **_kwargs: object) -> object:
        url = "http://x"
        raise urllib.error.HTTPError(url, 401, "no", Message(), io.BytesIO())

    monkeypatch.setattr(doctor.urllib.request, "urlopen", raise_http)
    assert doctor.fetch_status("http://x", {}, 1.0) == 401

    def raise_url(*_args: object, **_kwargs: object) -> object:
        reason = "refused"
        raise urllib.error.URLError(reason)

    monkeypatch.setattr(doctor.urllib.request, "urlopen", raise_url)
    with pytest.raises(OSError, match="refused"):
        doctor.fetch_status("http://x", {}, 1.0)


def test_collect_runs_every_check_and_skips_network_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A valid configuration yields all checks and no network access offline."""
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: pytest.fail("network"))

    checks = doctor.collect_doctor_checks(_environ(tmp_path), offline=True)

    assert [check.name for check in checks] == [
        "Python",
        "Environment file",
        "Settings",
        "Telegram token",
        "ffmpeg",
        "Animated stickers",
        "Database",
        "LLM server",
        "audiodoc",
    ]
    assert not [check for check in checks if check.status == "FAIL"]


def test_collect_skips_dependent_checks_for_invalid_settings(tmp_path: Path) -> None:
    """Invalid settings fail once and the dependent checks are marked skipped."""
    checks = doctor.collect_doctor_checks(
        _environ(tmp_path, SUPERVISOR_ID="x"), offline=True
    )
    by_name: dict[str, doctor.DiagnosticCheck] = {check.name: check for check in checks}

    assert by_name["Settings"].status == "FAIL"
    for name in ("Database", "LLM server", "audiodoc"):
        assert by_name[name].status == "WARN"
        assert "invalid" in by_name[name].message
