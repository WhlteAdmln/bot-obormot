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
    """``version`` prints the package version."""
    monkeypatch.setattr(cli, "package_version", lambda _name: "9.8.7")

    assert cli.main(["version"]) == 0
    expected_out = "bot-obormot 9.8.7\n"
    assert capsys.readouterr().out == expected_out


def test_missing_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """A missing subcommand exits with status 2."""
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    expected_code = 2
    assert exit_info.value.code == expected_code
    expected_fragment = "usage"
    assert expected_fragment in capsys.readouterr().err.lower()


def test_run_starts_the_bot_with_the_env_file(
    monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    """``run`` forwards ``--env-file`` to the application entry point."""
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
    """Invalid settings end ``run`` with a usage error, not a traceback."""
    _ = home

    async def failing_run_bot(env_file: Path | None = None) -> None:
        _ = env_file
        raise ConfigError(["SUPERVISOR_ID must be an integer"])

    monkeypatch.setattr(cli, "run_bot", failing_run_bot)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["run"])

    expected_code = 2
    assert exit_info.value.code == expected_code
    expected_fragment = "SUPERVISOR_ID"
    assert expected_fragment in capsys.readouterr().err


def test_python_dash_m_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``python -m bot_obormot`` behaves like the console script."""
    monkeypatch.setattr(cli, "package_version", lambda _name: "1.2.3")
    monkeypatch.setattr(sys, "argv", ["bot_obormot", "version"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("bot_obormot", run_name="__main__")

    assert exit_info.value.code == 0
    expected_fragment = "bot-obormot 1.2.3"
    assert expected_fragment in capsys.readouterr().out


def test_config_check_shows_template_placeholder_errors(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    """The example file fails with the expected placeholder problems."""
    _ = home

    assert cli.main(["config", "check", "--env-file", str(ENV_EXAMPLE)]) == 1

    output = capsys.readouterr().out
    expected_fragment = "Configuration has problems:"
    assert expected_fragment in output
    expected_fragment = "SUPERVISOR_ID"
    assert expected_fragment in output
    expected_fragment = "BOT_TOKEN"
    assert expected_fragment in output
    expected_fragment = "REPLACE_WITH_NUMERIC_TELEGRAM_ID"
    assert expected_fragment not in output


def test_config_check_never_prints_secrets(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    """Problem lines name the setting but not its value."""
    _ = home
    cli.os.environ.update(
        {"BOT_TOKEN": VALID_TOKEN, "SUPERVISOR_ID": "top-secret", "LLM_TIMEOUT": "0"}
    )

    assert cli.main(["config", "check"]) == 1

    output = capsys.readouterr().out
    expected_fragment = "SUPERVISOR_ID"
    assert expected_fragment in output
    expected_fragment = "top-secret"
    assert expected_fragment not in output
    assert VALID_TOKEN not in output


def test_config_check_accepts_a_valid_configuration(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    """A complete configuration passes."""
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
    """``init`` writes a protected .env and prints three next steps."""
    assert cli.main(["init", "--token", VALID_TOKEN, "--supervisor", "7"]) == 0

    env_path = home / ".env"
    expected_number = 0o600
    assert env_path.stat().st_mode & 0o777 == expected_number
    expected_fragment = "SUPERVISOR_ID=7"
    assert expected_fragment in env_path.read_text(encoding="utf-8")
    output = capsys.readouterr().out
    assert f"Created configuration: {env_path}" in output
    expected_fragment = "  1. "
    assert expected_fragment in output
    expected_fragment = "  2. "
    assert expected_fragment in output
    expected_fragment = "  3. "
    assert expected_fragment in output


def test_init_refuses_to_overwrite_without_force(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    """An existing file is kept; ``--force`` replaces it."""
    home.mkdir()
    (home / ".env").write_text("OLD=1\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["init"])

    expected_code = 2
    assert exit_info.value.code == expected_code
    expected_fragment = "--force"
    assert expected_fragment in capsys.readouterr().err
    expected_text = "OLD=1\n"
    assert (home / ".env").read_text(encoding="utf-8") == expected_text

    assert cli.main(["init", "--force"]) == 0
    expected_fragment = "OLD=1"
    assert expected_fragment not in (home / ".env").read_text(encoding="utf-8")


def test_init_rejects_an_invalid_token(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    """A malformed token is reported and no file is created."""
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["init", "--token", "bad"])

    expected_code = 2
    assert exit_info.value.code == expected_code
    expected_fragment = "token"
    assert expected_fragment in capsys.readouterr().err
    assert not (home / ".env").exists()


def test_doctor_prints_all_lines_and_fails_on_fail(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
) -> None:
    """The exit status is 1 when any check fails."""
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
    """``--quiet`` prints only warnings and failures."""
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
    """``--print`` renders the unit and writes nothing."""
    assert cli.main(["service", "install", "--print"]) == 0

    output = capsys.readouterr().out
    assert f'ExecStart="{home}/.venv/bin/bot-obormot" run' in output
    expected_fragment = "BOT_OBORMOT_HOME"
    assert expected_fragment in output
    assert not (home / ".config").exists()


def test_service_install_writes_the_user_unit_and_prints_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    home: Path,
    tmp_path: Path,
) -> None:
    """The default install writes a user unit and never starts the service."""
    _ = home
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))

    assert cli.main(["service", "install"]) == 0

    unit = tmp_path / "user" / ".config" / "systemd" / "user" / "bot-obormot.service"
    assert unit.is_file()
    output = capsys.readouterr().out
    expected_fragment = "was not enabled or started"
    assert expected_fragment in output
    expected_fragment = "systemctl --user daemon-reload"
    assert expected_fragment in output
    expected_fragment = "systemctl --user enable --now bot-obormot.service"
    assert expected_fragment in output

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
    """Uninstall removes the file but leaves the running service alone."""
    _ = home
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "user"))
    assert cli.main(["service", "uninstall"]) == 0
    expected_fragment = "No systemd unit is installed."
    assert expected_fragment in capsys.readouterr().out

    cli.main(["service", "install"])
    capsys.readouterr()

    assert cli.main(["service", "uninstall"]) == 0
    output = capsys.readouterr().out
    expected_fragment = "was not stopped"
    assert expected_fragment in output
    expected_fragment = "disable --now bot-obormot.service"
    assert expected_fragment in output


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
    expected_fragment = "systemctl was not found"
    assert expected_fragment in capsys.readouterr().err, "the error must name systemctl"
