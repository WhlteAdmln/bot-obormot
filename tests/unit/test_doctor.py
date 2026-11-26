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


def _environ(tmp_path: Path, **overrides: str) -> dict[str, str]:
    """Build a valid environment rooted in a temporary home."""
    values = {
        "BOT_OBORMOT_HOME": str(tmp_path),
        "HOME": str(tmp_path),
        "BOT_TOKEN": "123456789:" + "A" * 35,
        "SUPERVISOR_ID": "42",
    }
    values.update(overrides)
    return values


def test_check_python_version_passes_on_the_running_interpreter() -> None:
    expected_status = "OK"
    result = doctor.check_python_version()
    assert result.status == expected_status, "the running interpreter was rejected"


def test_check_python_version_fails_below_3_11(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 10, 14, "final", 0))
    expected_status = "FAIL"
    result = doctor.check_python_version()
    assert result.status == expected_status, "Python 3.10 was accepted"


def test_check_python_version_names_the_minimum_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "version_info", (3, 9, 7, "candidate", 2))
    minimum_version = "3.11"
    result = doctor.check_python_version()
    assert minimum_version in result.message, "the minimum version is not named"


def test_check_env_file_accepts_private_permissions(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("LOG_ÉTAPE=debug\n", encoding="utf-8")
    env_path.chmod(0o600)
    expected_status = "OK"
    result = doctor.check_env_file(_environ(tmp_path))
    assert result.status == expected_status, "a private .env file was not accepted"


def test_check_env_file_warns_when_the_file_is_missing(tmp_path: Path) -> None:
    expected_status = "WARN"
    result = doctor.check_env_file(_environ(tmp_path))
    assert result.status == expected_status, "a missing .env file gave no warning"


def test_check_env_file_mentions_the_process_environment_when_missing(
    tmp_path: Path,
) -> None:
    environment_source = "process environment"
    result = doctor.check_env_file(_environ(tmp_path))
    assert environment_source in result.message, "the fallback source is not named"


def test_check_env_file_warns_when_others_can_read_it(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("Z_9=\t~\n", encoding="utf-8")
    env_path.chmod(0o644)
    expected_status = "WARN"
    result = doctor.check_env_file(_environ(tmp_path))
    assert result.status == expected_status, "an open .env file gave no warning"


def test_check_env_file_suggests_chmod_for_open_permissions(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("ÆØÅ=1\n", encoding="utf-8")
    env_path.chmod(0o604)
    permission_hint = "chmod 600"
    result = doctor.check_env_file(_environ(tmp_path))
    assert permission_hint in result.message, "the permission fix is not suggested"


def test_check_env_file_fails_for_a_directory(tmp_path: Path) -> None:
    (tmp_path / ".env").mkdir()
    expected_status = "FAIL"
    result = doctor.check_env_file(_environ(tmp_path))
    assert result.status == expected_status, "a .env directory was not rejected"


def test_check_settings_accepts_a_valid_environment(tmp_path: Path) -> None:
    expected_status = "OK"
    result, _settings = doctor.check_settings(_environ(tmp_path))
    assert result.status == expected_status, "a valid environment was rejected"


def test_check_settings_returns_settings_for_a_valid_environment(
    tmp_path: Path,
) -> None:
    _result, settings = doctor.check_settings(_environ(tmp_path))
    assert settings is not None, "no settings were returned for a valid environment"


def test_check_settings_fails_for_invalid_fields(tmp_path: Path) -> None:
    environ = _environ(tmp_path, SUPERVISOR_ID="сорок два", LLM_TIMEOUT="-0.5")
    expected_status = "FAIL"
    result, _settings = doctor.check_settings(environ)
    assert result.status == expected_status, "invalid settings were accepted"


def test_check_settings_returns_no_settings_for_invalid_fields(tmp_path: Path) -> None:
    environ = _environ(tmp_path, SUPERVISOR_ID="0x2A", LLM_TIMEOUT="0")
    _result, settings = doctor.check_settings(environ)
    assert settings is None, "settings were returned for an invalid environment"


@pytest.mark.parametrize("field", ["SUPERVISOR_ID", "LLM_TIMEOUT"])
def test_check_settings_names_every_invalid_field(tmp_path: Path, field: str) -> None:
    environ = _environ(tmp_path, SUPERVISOR_ID="4 2", LLM_TIMEOUT="0")
    result, _settings = doctor.check_settings(environ)
    assert field in result.message, f"the invalid field {field} is not named"


def test_check_settings_hides_invalid_values(tmp_path: Path) -> None:
    leaked_value = "s3cr3t-Wert-ß"
    environ = _environ(tmp_path, SUPERVISOR_ID=leaked_value, LLM_TIMEOUT="0")
    result, _settings = doctor.check_settings(environ)
    assert leaked_value not in result.message, "an invalid value leaked into the report"


@pytest.mark.parametrize(
    ("token", "status"),
    [
        ("123456789:" + "A" * 35, "OK"),
        ("", "FAIL"),
        ("YOUR_TELEGRAM_BOT_TOKEN", "FAIL"),
        ("not-a-token", "FAIL"),
    ],
)
def test_check_bot_token_validates_the_format(token: str, status: str) -> None:
    result = doctor.check_bot_token({"BOT_TOKEN": token})
    assert result.status == status, "the token format was judged wrongly"


@pytest.mark.parametrize(
    "token",
    ["123456789:" + "A" * 35, "YOUR_TELEGRAM_BOT_TOKEN", "not-a-token"],
)
def test_check_bot_token_does_not_echo_the_token(token: str) -> None:
    result = doctor.check_bot_token({"BOT_TOKEN": token})
    assert token not in result.message, "the token was echoed in the report"


def test_check_ffmpeg_passes_when_both_programs_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda name: f"/opt/ff/{name}")
    expected_status = "OK"
    result = doctor.check_ffmpeg()
    assert result.status == expected_status, "present programs were not accepted"


def test_check_ffmpeg_warns_about_a_missing_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: None)
    expected_status = "WARN"
    result = doctor.check_ffmpeg()
    assert result.status == expected_status, "missing programs gave no warning"


def test_check_ffmpeg_names_the_missing_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_program = "ffprobe"

    def which(name: str) -> str | None:
        return None if name == missing_program else "/usr/local/bin/ffmpeg"

    monkeypatch.setattr(doctor.shutil, "which", which)
    result = doctor.check_ffmpeg()
    assert missing_program in result.message, "the missing program is not named"


def test_check_ffmpeg_does_not_list_a_present_program(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_program = "ffprobe"

    def which(name: str) -> str | None:
        return None if name == missing_program else "/snap/bin/ffmpeg"

    monkeypatch.setattr(doctor.shutil, "which", which)
    present_program = "ffmpeg,"
    result = doctor.check_ffmpeg()
    assert present_program not in result.message, "a present program is listed"


def test_check_tgs_support_passes_with_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "tgs_support_available", lambda: True)
    expected_status = "OK"
    result = doctor.check_tgs_support()
    assert result.status == expected_status, "the installed extra was not accepted"


def test_check_tgs_support_warns_without_the_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "tgs_support_available", lambda: False)
    expected_status = "WARN"
    result = doctor.check_tgs_support()
    assert result.status == expected_status, "the missing extra gave no warning"


def test_check_tgs_support_names_the_extra_to_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "tgs_support_available", lambda: False)
    install_extra = "bot-obormot[tgs]"
    result = doctor.check_tgs_support()
    assert install_extra in result.message, "the extra to install is not named"


def test_check_database_path_accepts_a_new_nested_path(tmp_path: Path) -> None:
    settings = Settings(DATABASE_PATH=str(tmp_path / "новая" / "data" / "bot.db"))
    expected_status = "OK"
    result = doctor.check_database_path(settings)
    assert result.status == expected_status, "a creatable path was rejected"


def test_check_database_path_accepts_an_existing_file(tmp_path: Path) -> None:
    existing = tmp_path / "obormot 2.sqlite3"
    existing.write_text("", encoding="utf-8")
    settings = Settings(DATABASE_PATH=str(existing))
    expected_status = "OK"
    result = doctor.check_database_path(settings)
    assert result.status == expected_status, "an existing database file was rejected"


def test_check_database_path_fails_without_write_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(DATABASE_PATH=str(tmp_path / "ro" / "x.db"))
    monkeypatch.setattr(doctor.os, "access", lambda _path, _mode: False)
    expected_status = "FAIL"
    result = doctor.check_database_path(settings)
    assert result.status == expected_status, "a read-only location was accepted"


def test_check_database_path_names_the_setting_without_write_access(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settings = Settings(DATABASE_PATH=str(tmp_path / "Ünïcode" / "bot.db"))
    monkeypatch.setattr(doctor.os, "access", lambda _path, _mode: False)
    setting_name = "DATABASE_PATH"
    result = doctor.check_database_path(settings)
    assert setting_name in result.message, "the setting to fix is not named"


def test_check_llm_server_passes_when_the_server_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 200)
    settings = Settings(LLM_BASE_URL="http://llm.test:8080/v1", LLM_API_KEY="k")
    expected_status = "OK"
    result = doctor.check_llm_server(settings, offline=False)
    assert result.status == expected_status, "an answering server was rejected"


def test_check_llm_server_requests_the_models_with_the_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, Mapping[str, str]]] = []

    def fake_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
        _ = timeout
        calls.append((url, headers))
        return 200

    monkeypatch.setattr(doctor, "fetch_status", fake_status)
    settings = Settings(LLM_BASE_URL="http://llm.test:8080/v1", LLM_API_KEY="kЁy-7")
    expected_calls = [
        ("http://llm.test:8080/v1/models", {"Authorization": "Bearer kЁy-7"})
    ]
    doctor.check_llm_server(settings, offline=False)
    assert calls == expected_calls, "the models endpoint was not requested correctly"


def test_check_llm_server_fails_for_an_error_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 503)
    settings = Settings(LLM_BASE_URL="https://llm.example:9443/v1")
    expected_status = "FAIL"
    result = doctor.check_llm_server(settings, offline=False)
    assert result.status == expected_status, "an error status was accepted"


def test_check_llm_server_fails_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(*_args: object) -> int:
        message = "connection refused"
        raise OSError(message)

    monkeypatch.setattr(doctor, "fetch_status", unreachable)
    settings = Settings(LLM_BASE_URL="http://10.0.0.7:11434/v1")
    expected_status = "FAIL"
    result = doctor.check_llm_server(settings, offline=False)
    assert result.status == expected_status, "an unreachable server was accepted"


def test_check_llm_server_hides_the_api_key_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable(*_args: object) -> int:
        message = "no route to host"
        raise OSError(message)

    monkeypatch.setattr(doctor, "fetch_status", unreachable)
    settings = Settings(LLM_BASE_URL="http://llm.test:8080/v1", LLM_API_KEY="q-Ω")
    auth_scheme = "Bearer"
    result = doctor.check_llm_server(settings, offline=False)
    assert auth_scheme not in result.message, "the auth header leaked into the report"


def test_check_llm_server_passes_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 500)
    settings = Settings(LLM_BASE_URL="http://llm.test:8080/v1")
    expected_status = "OK"
    result = doctor.check_llm_server(settings, offline=True)
    assert result.status == expected_status, "the offline check did not pass"


def test_check_llm_server_reports_the_offline_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 500)
    settings = Settings(LLM_BASE_URL="http://llm.test:8080/v1")
    offline_note = "offline"
    result = doctor.check_llm_server(settings, offline=True)
    assert offline_note in result.message, "the offline skip is not reported"


def test_check_llm_server_makes_no_request_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
        _ = headers, timeout
        calls.append(url)
        return 200

    monkeypatch.setattr(doctor, "fetch_status", fake_status)
    settings = Settings(LLM_BASE_URL="http://llm.test:8080/v1")
    expected_empty: list[str] = []
    doctor.check_llm_server(settings, offline=True)
    assert calls == expected_empty, "the offline check made a request"


def test_check_audiodoc_passes_when_the_service_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 200)
    settings = Settings(AUDIODOC_URL="http://audio.test:8000")
    expected_status = "OK"
    result = doctor.check_audiodoc(settings, offline=False)
    assert result.status == expected_status, "an answering service was rejected"


def test_check_audiodoc_requests_the_health_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
        _ = headers, timeout
        seen.append(url)
        return 200

    monkeypatch.setattr(doctor, "fetch_status", fake_status)
    settings = Settings(AUDIODOC_URL="http://user:pw@audio.test:8000")
    expected_urls = ["http://user:pw@audio.test:8000/health"]
    doctor.check_audiodoc(settings, offline=False)
    assert seen == expected_urls, "the health endpoint was not requested"


def test_check_audiodoc_hides_url_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 200)
    url_credential = "pässwort-31"
    settings = Settings(AUDIODOC_URL=f"http://ivan:{url_credential}@audio.test:8000")
    result = doctor.check_audiodoc(settings, offline=False)
    assert url_credential not in result.message, "a URL credential leaked"


def test_check_audiodoc_warns_for_an_error_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 500)
    settings = Settings(AUDIODOC_URL="https://audio.example:8443")
    expected_status = "WARN"
    result = doctor.check_audiodoc(settings, offline=False)
    assert result.status == expected_status, "an error status gave no warning"


def test_check_audiodoc_passes_when_not_configured() -> None:
    expected_status = "OK"
    result = doctor.check_audiodoc(Settings(), offline=False)
    assert result.status == expected_status, "an unconfigured service was rejected"


def test_check_audiodoc_passes_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 500)
    settings = Settings(AUDIODOC_URL="http://192.168.1.50:8000")
    expected_status = "OK"
    result = doctor.check_audiodoc(settings, offline=True)
    assert result.status == expected_status, "the offline check did not pass"


def test_fetch_status_rejects_other_schemes() -> None:
    expected = "Only http and https URLs are supported."
    with pytest.raises(ValueError, match="https") as caught:
        doctor.fetch_status("file:///etc/passwd", {}, 1.0)
    assert str(caught.value) == expected, "a file URL was not rejected"


def test_fetch_status_returns_the_code_of_an_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_http(*_args: object, **_kwargs: object) -> object:
        url = "http://auth.test/models"
        raise urllib.error.HTTPError(url, 401, "no", Message(), io.BytesIO())

    monkeypatch.setattr(doctor.urllib.request, "urlopen", raise_http)
    expected_code = 401
    code = doctor.fetch_status("http://auth.test/models", {}, 2.5)
    assert code == expected_code, "the HTTP error code was not returned"


def test_fetch_status_raises_os_error_when_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_url(*_args: object, **_kwargs: object) -> object:
        reason = "refused"
        raise urllib.error.URLError(reason)

    monkeypatch.setattr(doctor.urllib.request, "urlopen", raise_url)
    expected = "refused"
    with pytest.raises(OSError, match="refused") as caught:
        doctor.fetch_status("https://down.test:4443/health", {}, 0.25)
    assert str(caught.value) == expected, "the unreachable reason was not kept"


def test_collect_runs_every_check_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 200)
    expected_names = [
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
    checks = doctor.collect_doctor_checks(_environ(tmp_path), offline=True)
    names = [check.name for check in checks]
    assert names == expected_names, "the checks differ from the expected order"


def test_collect_reports_no_failure_for_a_valid_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(doctor, "fetch_status", lambda *_args: 200)
    failed_status = "FAIL"
    expected_empty: list[doctor.DiagnosticCheck] = []
    checks = doctor.collect_doctor_checks(_environ(tmp_path), offline=True)
    failed = [check for check in checks if check.status == failed_status]
    assert failed == expected_empty, "a valid environment produced failures"


def test_collect_makes_no_request_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[str] = []

    def fake_status(url: str, headers: Mapping[str, str], timeout: float) -> int:
        _ = headers, timeout
        calls.append(url)
        return 200

    monkeypatch.setattr(doctor, "fetch_status", fake_status)
    environ = _environ(tmp_path, AUDIODOC_URL="http://audio.test:8000")
    expected_empty: list[str] = []
    doctor.collect_doctor_checks(environ, offline=True)
    assert calls == expected_empty, "the offline run made a request"


def test_collect_fails_the_settings_check_for_invalid_settings(tmp_path: Path) -> None:
    environ = _environ(tmp_path, SUPERVISOR_ID="x")
    expected_status = "FAIL"
    checks = doctor.collect_doctor_checks(environ, offline=True)
    by_name = {check.name: check for check in checks}
    assert by_name["Settings"].status == expected_status, "bad settings passed"


@pytest.mark.parametrize("name", ["Database", "LLM server", "audiodoc"])
def test_collect_warns_on_dependent_checks_for_invalid_settings(
    tmp_path: Path, name: str
) -> None:
    environ = _environ(tmp_path, SUPERVISOR_ID="-")
    expected_status = "WARN"
    checks = doctor.collect_doctor_checks(environ, offline=True)
    by_name = {check.name: check for check in checks}
    assert by_name[name].status == expected_status, f"{name} was not skipped"


@pytest.mark.parametrize("name", ["Database", "LLM server", "audiodoc"])
def test_collect_explains_skipped_checks_for_invalid_settings(
    tmp_path: Path, name: str
) -> None:
    environ = _environ(tmp_path, SUPERVISOR_ID="12.5x")
    invalid_note = "invalid"
    checks = doctor.collect_doctor_checks(environ, offline=True)
    by_name = {check.name: check for check in checks}
    assert invalid_note in by_name[name].message, f"{name} does not explain the skip"
