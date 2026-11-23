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
    expected_status = "OK"
    assert doctor.check_python_version().status == expected_status

    monkeypatch.setattr(sys, "version_info", (3, 10, 0, "final", 0))
    result = doctor.check_python_version()

    expected_status = "FAIL"
    assert result.status == expected_status
    expected_fragment = "3.11"
    assert expected_fragment in result.message


def test_env_file_ok_with_private_permissions(tmp_path: Path) -> None:
    """A private .env file passes."""
    env_path = tmp_path / ".env"
    env_path.write_text("A=1\n", encoding="utf-8")
    env_path.chmod(0o600)

    expected_status = "OK"
    assert doctor.check_env_file(_environ(tmp_path)).status == expected_status


def test_env_file_warns_when_open_or_missing(tmp_path: Path) -> None:
    """Open permissions and a missing file are warnings, not failures."""
    missing = doctor.check_env_file(_environ(tmp_path))
    expected_status = "WARN"
    assert missing.status == expected_status
    expected_fragment = "process environment"
    assert expected_fragment in missing.message

    env_path = tmp_path / ".env"
    env_path.write_text("A=1\n", encoding="utf-8")
    env_path.chmod(0o644)
    opened = doctor.check_env_file(_environ(tmp_path))
    expected_status = "WARN"
    assert opened.status == expected_status
    expected_fragment = "chmod 600"
    assert expected_fragment in opened.message


def test_env_file_fails_for_a_directory(tmp_path: Path) -> None:
    """A directory in place of the file is a failure."""
    (tmp_path / ".env").mkdir()

    expected_status = "FAIL"
    assert doctor.check_env_file(_environ(tmp_path)).status == expected_status


def test_settings_success_and_failure_without_secrets(tmp_path: Path) -> None:
    """Invalid settings are listed by name and values are not echoed."""
    ok_check, settings = doctor.check_settings(_environ(tmp_path))
    expected_status = "OK"
    assert ok_check.status == expected_status
    assert settings is not None

    bad_check, bad_settings = doctor.check_settings(
        _environ(tmp_path, SUPERVISOR_ID="secret-value", LLM_TIMEOUT="0")
    )
    expected_status = "FAIL"
    assert bad_check.status == expected_status
    assert bad_settings is None
    expected_fragment = "SUPERVISOR_ID"
    assert expected_fragment in bad_check.message
    expected_fragment = "LLM_TIMEOUT"
    assert expected_fragment in bad_check.message
    expected_fragment = "secret-value"
    assert expected_fragment not in bad_check.message


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
    expected_status = "OK"
    assert doctor.check_ffmpeg().status == expected_status

    missing = "ffprobe"

    def which(name: str) -> str | None:
        return None if name == missing else "/bin/x"

    monkeypatch.setattr(doctor.shutil, "which", which)
    result = doctor.check_ffmpeg()
    expected_status = "WARN"
    assert result.status == expected_status
    expected_fragment = "ffprobe"
    assert expected_fragment in result.message
    expected_fragment = "ffmpeg,"
    assert expected_fragment not in result.message


def test_tgs_support_success_and_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """The optional extra is reported as a warning when it is absent."""
    monkeypatch.setattr(doctor, "tgs_support_available", lambda: True)
    expected_status = "OK"
    assert doctor.check_tgs_support().status == expected_status

    monkeypatch.setattr(doctor, "tgs_support_available", lambda: False)
    result = doctor.check_tgs_support()
    expected_status = "WARN"
    assert result.status == expected_status
    expected_fragment = "bot-obormot[tgs]"
    assert expected_fragment in result.message


def test_database_path_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A creatable path passes; an unwritable ancestor fails."""
    good = Settings(DATABASE_PATH=str(tmp_path / "new" / "data" / "bot.db"))
    expected_status = "OK"
    assert doctor.check_database_path(good).status == expected_status

    existing = tmp_path / "bot.db"
    existing.write_text("", encoding="utf-8")
    existing_settings = Settings(DATABASE_PATH=str(existing))
    expected_status = "OK"
    assert doctor.check_database_path(existing_settings).status == expected_status

    monkeypatch.setattr(doctor.os, "access", lambda _path, _mode: False)
    result = doctor.check_database_path(good)
    expected_status = "FAIL"
    assert result.status == expected_status
    expected_fragment = "DATABASE_PATH"
    assert expected_fragment in result.message


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

    expected_status = "OK"
    assert doctor.check_llm_server(settings, offline=False).status == expected_status
    assert calls == [("http://llm.test:8080/v1/models", {"Authorization": "Bearer k"})]

    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 503)
    expected_status = "FAIL"
    assert doctor.check_llm_server(settings, offline=False).status == expected_status

    def unreachable(*_args: object) -> int:
        message = "connection refused"
        raise OSError(message)

    monkeypatch.setattr(doctor, "fetch_status", unreachable)
    failed = doctor.check_llm_server(settings, offline=False)
    expected_status = "FAIL"
    assert failed.status == expected_status
    expected_fragment = "Bearer"
    assert expected_fragment not in failed.message

    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: pytest.fail("network"))
    skipped = doctor.check_llm_server(settings, offline=True)
    expected_status = "OK"
    assert skipped.status == expected_status
    expected_fragment = "offline"
    assert expected_fragment in skipped.message


def test_audiodoc_success_failure_unconfigured_and_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audiodoc is optional: unreachable is a warning, unset is fine."""
    seen: list[str] = []

    def fake_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
        _ = headers, timeout
        seen.append(url)
        return 200

    monkeypatch.setattr(doctor, "fetch_status", fake_status)
    configured = Settings(AUDIODOC_URL="http://user:pw@audio.test:8000")

    result = doctor.check_audiodoc(configured, offline=False)
    expected_status = "OK"
    assert result.status == expected_status
    assert seen == ["http://user:pw@audio.test:8000/health"]
    expected_fragment = "pw"
    assert expected_fragment not in result.message

    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 500)
    expected_status = "WARN"
    assert doctor.check_audiodoc(configured, offline=False).status == expected_status

    expected_status = "OK"
    assert doctor.check_audiodoc(Settings(), offline=False).status == expected_status
    expected_status = "OK"
    assert doctor.check_audiodoc(configured, offline=True).status == expected_status


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
    expected_fetch_status = 401
    assert doctor.fetch_status("http://x", {}, 1.0) == expected_fetch_status

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
    expected_status = "FAIL"
    expected_empty = []
    assert [
        check for check in checks if check.status == expected_status
    ] == expected_empty, "expected an empty list"


def test_collect_skips_dependent_checks_for_invalid_settings(tmp_path: Path) -> None:
    """Invalid settings fail once and the dependent checks are marked skipped."""
    checks = doctor.collect_doctor_checks(
        _environ(tmp_path, SUPERVISOR_ID="x"), offline=True
    )
    by_name: dict[str, doctor.DiagnosticCheck] = {check.name: check for check in checks}

    expected_status = "FAIL"
    assert by_name["Settings"].status == expected_status
    for name in ("Database", "LLM server", "audiodoc"):
        expected_status = "WARN"
        assert by_name[name].status == expected_status
        expected_fragment = "invalid"
        assert expected_fragment in by_name[name].message
