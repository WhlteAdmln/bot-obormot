# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the bot-obormot command-line interface."""

import runpy
import sys
from pathlib import Path

import pytest

from bot_obormot import cli
from bot_obormot.common import process
from bot_obormot.doctor import DiagnosticCheck
from bot_obormot.settings import ConfigError
from tests.support.program_runs import FakeProgramRun

VALID_TOKEN = "123456789:" + "A" * 35
ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


@pytest.fixture(name="home")
def fixture_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolate the process environment and point the app home at a temp dir."""
    home_dir = tmp_path / "home"
    monkeypatch.setattr(
        cli.os,
        "environ",
        {"BOT_OBORMOT_HOME": str(home_dir), "HOME": str(tmp_path)},
    )
    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: tmp_path / "cwd"))
    return home_dir


def test_version_prints_the_installed_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "package_version", lambda _name: "9.8.7")

    assert cli.main(["version"]) == 0
    expected_out = "bot-obormot 9.8.7\n"
    assert capsys.readouterr().out == expected_out


def test_missing_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    expected_code = 2
    assert exit_info.value.code == expected_code
    usage_word = "usage"
    assert usage_word in capsys.readouterr().err.lower()


def test_run_starts_the_bot_with_the_env_file(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    _ = home
    received: list[Path | None] = []

    async def fake_run_bot(env_file: Path | None = None) -> None:
        received.append(env_file)

    monkeypatch.setattr(cli, "run_bot", fake_run_bot)

    assert cli.main(["run", "--env-file", "custom.env"]) == 0
    assert cli.main(["run"]) == 0
    assert received == [Path("custom.env"), None]


def test_run_reports_configuration_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
) -> None:
    _ = home

    async def failing_run_bot(env_file: Path | None = None) -> None:
        _ = env_file
        raise ConfigError(["SUPERVISOR_ID must be an integer"])

    monkeypatch.setattr(cli, "run_bot", failing_run_bot)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["run"])

    expected_code = 2
    assert exit_info.value.code == expected_code
    setting_name = "SUPERVISOR_ID"
    assert setting_name in capsys.readouterr().err


def test_python_dash_m_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "package_version", lambda _name: "1.2.3")
    monkeypatch.setattr(sys, "argv", ["bot_obormot", "version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("bot_obormot", run_name="__main__")

    assert exit_info.value.code == 0
    version_line = "bot-obormot 1.2.3"
    assert version_line in capsys.readouterr().out


def test_config_check_shows_template_placeholder_errors(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    _ = home

    assert cli.main(["config", "check", "--env-file", str(ENV_EXAMPLE)]) == 1

    output = capsys.readouterr().out
    problems_header = "Configuration has problems:"
    assert problems_header in output
    supervisor_name = "SUPERVISOR_ID"
    assert supervisor_name in output
    bot_setting_name = "BOT_TOKEN"
    assert bot_setting_name in output
    supervisor_placeholder = "REPLACE_WITH_NUMERIC_TELEGRAM_ID"
    assert supervisor_placeholder not in output


def test_config_check_never_prints_secrets(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    _ = home
    cli.os.environ.update(
        {"BOT_TOKEN": VALID_TOKEN, "SUPERVISOR_ID": "top-secret", "LLM_TIMEOUT": "0"}
    )

    assert cli.main(["config", "check"]) == 1

    output = capsys.readouterr().out
    setting_name = "SUPERVISOR_ID"
    assert setting_name in output
    leaked_value = "top-secret"
    assert leaked_value not in output
    assert VALID_TOKEN not in output


def test_config_check_accepts_a_valid_configuration(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    home.mkdir()
    (home / ".env").write_text(
        f"BOT_TOKEN={VALID_TOKEN}\nSUPERVISOR_ID=42\n", encoding="utf-8"
    )

    assert cli.main(["config", "check"]) == 0
    expected_out = "Configuration is valid.\n"
    assert capsys.readouterr().out == expected_out


def test_init_creates_the_file_and_prints_next_steps(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    assert cli.main(["init", "--token", VALID_TOKEN, "--supervisor", "7"]) == 0

    env_path = home / ".env"
    expected_number = 0o600
    assert env_path.stat().st_mode & 0o777 == expected_number
    supervisor_line = "SUPERVISOR_ID=7"
    assert supervisor_line in env_path.read_text(encoding="utf-8")
    output = capsys.readouterr().out
    assert f"Created configuration: {env_path}" in output
    first_step = "  1. "
    assert first_step in output
    second_step = "  2. "
    assert second_step in output
    third_step = "  3. "
    assert third_step in output


def test_init_refuses_to_overwrite_without_force(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    home.mkdir()
    (home / ".env").write_text("OLD=1\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["init"])

    expected_code = 2
    assert exit_info.value.code == expected_code
    force_option = "--force"
    assert force_option in capsys.readouterr().err
    expected_text = "OLD=1\n"
    assert (home / ".env").read_text(encoding="utf-8") == expected_text

    assert cli.main(["init", "--force"]) == 0
    old_line = "OLD=1"
    assert old_line not in (home / ".env").read_text(encoding="utf-8")


def test_init_rejects_an_invalid_token(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["init", "--token", "bad"])

    expected_code = 2
    assert exit_info.value.code == expected_code
    bot_credential_word = "token"
    assert bot_credential_word in capsys.readouterr().err
    assert not (home / ".env").exists()


def test_doctor_prints_all_lines_and_fails_on_fail(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
) -> None:
    _ = home
    checks = [
        DiagnosticCheck("Python", "OK", "fine"),
        DiagnosticCheck("ffmpeg", "WARN", "missing"),
        DiagnosticCheck("Settings", "FAIL", "broken"),
    ]
    offline_values: list[bool] = []

    def fake_collect(
        _environ: object, *, offline: bool = False
    ) -> list[DiagnosticCheck]:
        offline_values.append(offline)
        return checks

    monkeypatch.setattr(cli, "collect_doctor_checks", fake_collect)

    assert cli.main(["doctor", "--offline"]) == 1
    assert offline_values == [True]
    assert capsys.readouterr().out.splitlines() == [
        "OK   Python: fine",
        "WARN ffmpeg: missing",
        "FAIL Settings: broken",
    ]


def test_doctor_quiet_hides_ok_lines_and_succeeds_without_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
) -> None:
    _ = home
    monkeypatch.setattr(
        cli,
        "collect_doctor_checks",
        lambda *_args, **_kwargs: [
            DiagnosticCheck("Python", "OK", "fine"),
            DiagnosticCheck("ffmpeg", "WARN", "missing"),
        ],
    )

    assert cli.main(["doctor", "--quiet"]) == 0
    expected_out = "WARN ffmpeg: missing\n"
    assert capsys.readouterr().out == expected_out


def test_service_install_print_only_prints_the_unit(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    assert cli.main(["service", "install", "--print"]) == 0

    output = capsys.readouterr().out
    assert f'ExecStart="{home}/.venv/bin/bot-obormot" run' in output
    home_variable = "BOT_OBORMOT_HOME"
    assert home_variable in output
    assert not (home / ".config").exists()


def test_service_install_writes_the_user_unit_and_prints_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    tmp_path: Path,
) -> None:
    _ = home
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))

    assert cli.main(["service", "install"]) == 0

    unit = tmp_path / "user" / ".config" / "systemd" / "user" / "bot-obormot.service"
    assert unit.is_file()
    output = capsys.readouterr().out
    not_started_note = "was not enabled or started"
    assert not_started_note in output
    reload_command = "systemctl --user daemon-reload"
    assert reload_command in output
    enable_command = "systemctl --user enable --now bot-obormot.service"
    assert enable_command in output

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["service", "install"])
    expected_code = 2
    assert exit_info.value.code == expected_code


def test_service_uninstall_removes_the_unit_and_prints_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    tmp_path: Path,
) -> None:
    _ = home
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))
    assert cli.main(["service", "uninstall"]) == 0
    no_unit_note = "No systemd unit is installed."
    assert no_unit_note in capsys.readouterr().out

    cli.main(["service", "install"])
    capsys.readouterr()

    assert cli.main(["service", "uninstall"]) == 0
    output = capsys.readouterr().out
    not_stopped_note = "was not stopped"
    assert not_stopped_note in output
    disable_command = "disable --now bot-obormot.service"
    assert disable_command in output


@pytest.fixture(name="systemctl")
def fixture_systemctl(monkeypatch: pytest.MonkeyPatch) -> FakeProgramRun:
    """Resolve systemctl and answer every run with exit code 3."""
    monkeypatch.setattr(process.shutil, "which", lambda _name: "/usr/bin/systemctl")
    fake = FakeProgramRun(returncode=3)
    monkeypatch.setattr(process.subprocess, "run", fake)
    return fake


def test_service_status_returns_the_systemctl_exit_code(
    systemctl: FakeProgramRun, home: Path
) -> None:
    _ = (systemctl, home)
    expected_code = 3
    actual = cli.main(["service", "status"])
    assert actual == expected_code, "status must return the systemctl exit code"


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            ["service", "status"],
            [
                "/usr/bin/systemctl",
                "--user",
                "status",
                "--no-pager",
                "bot-obormot.service",
            ],
        ),
        (
            ["service", "status", "--system"],
            ["/usr/bin/systemctl", "status", "--no-pager", "bot-obormot.service"],
        ),
    ],
    ids=["user", "system"],
)
def test_service_status_runs_a_read_only_systemctl_command(
    systemctl: FakeProgramRun, home: Path, arguments: list[str], expected: list[str]
) -> None:
    _ = home
    cli.main(arguments)
    assert systemctl.commands == [expected], "status must only read systemctl status"


def test_service_status_without_systemctl_exits_with_a_usage_error(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    _ = home
    monkeypatch.setattr(process.shutil, "which", lambda _name: None)
    expected_code = 2
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["service", "status", "--system"])
    assert exit_info.value.code == expected_code, "missing systemctl must exit with 2"


def test_service_status_without_systemctl_names_the_program(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
) -> None:
    _ = home
    monkeypatch.setattr(process.shutil, "which", lambda _name: None)
    with pytest.raises(SystemExit):
        cli.main(["service", "status"])
    missing_systemctl_note = "systemctl was not found"
    assert missing_systemctl_note in capsys.readouterr().err, (
        "the error must name systemctl"
    )
