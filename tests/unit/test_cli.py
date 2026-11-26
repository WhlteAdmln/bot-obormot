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


@pytest.fixture(name="env_example")
def fixture_env_example() -> Path:
    """Return the configuration template of the repository."""
    return Path(__file__).resolve().parents[2] / ".env.example"


@pytest.fixture(name="user_home")
def fixture_user_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the user home directory, where systemd user units live, at a temp dir."""
    user_dir = tmp_path / "user"
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: user_dir))
    return user_dir


@pytest.fixture(name="received_env_files")
def fixture_received_env_files(monkeypatch: pytest.MonkeyPatch) -> list[Path | None]:
    """Replace the bot runner and record the env file of every run."""
    received: list[Path | None] = []

    async def fake_run_bot(env_file: Path | None = None) -> None:
        received.append(env_file)

    monkeypatch.setattr(cli, "run_bot", fake_run_bot)
    return received


@pytest.fixture(name="failing_bot")
def fixture_failing_bot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the bot runner with one that reports a configuration error."""

    async def failing_run_bot(env_file: Path | None = None) -> None:
        _ = env_file
        raise ConfigError(["SUPERVISOR_ID must be an integer"])

    monkeypatch.setattr(cli, "run_bot", failing_run_bot)


@pytest.fixture(name="offline_values")
def fixture_offline_values(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    """Answer doctor with an OK, a WARN and a FAIL check; record the offline flag."""
    checks = [
        DiagnosticCheck("Python", "OK", "fine"),
        DiagnosticCheck("ffmpeg", "WARN", "missing"),
        DiagnosticCheck("Settings", "FAIL", "broken"),
    ]
    received: list[bool] = []

    def fake_collect(
        _environ: object, *, offline: bool = False
    ) -> list[DiagnosticCheck]:
        received.append(offline)
        return checks

    monkeypatch.setattr(cli, "collect_doctor_checks", fake_collect)
    return received


@pytest.fixture(name="quiet_checks")
def fixture_quiet_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer doctor with an OK and a WARN check."""
    monkeypatch.setattr(
        cli,
        "collect_doctor_checks",
        lambda *_args, **_kwargs: [
            DiagnosticCheck("Python", "OK", "fine"),
            DiagnosticCheck("ffmpeg", "WARN", "missing"),
        ],
    )


@pytest.fixture(name="systemctl")
def fixture_systemctl(monkeypatch: pytest.MonkeyPatch) -> FakeProgramRun:
    """Resolve systemctl and answer every run with exit code 3."""
    monkeypatch.setattr(process.shutil, "which", lambda _name: "/usr/bin/systemctl")
    fake = FakeProgramRun(returncode=3)
    monkeypatch.setattr(process.subprocess, "run", fake)
    return fake


def test_version_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    installed = "9.8.7"
    monkeypatch.setattr(cli, "package_version", lambda _name: installed)
    arguments = ["version"]
    assert cli.main(arguments) == 0, "version must succeed"


def test_version_prints_the_installed_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    installed = "4.0.12"
    monkeypatch.setattr(cli, "package_version", lambda _name: installed)
    cli.main(["version"])
    expected_out = "bot-obormot 4.0.12\n"
    assert capsys.readouterr().out == expected_out, "version printed a wrong line"


def test_missing_command_exits_with_a_usage_error_code() -> None:
    arguments: list[str] = []
    expected_code = 2
    with pytest.raises(SystemExit) as exit_info:
        cli.main(arguments)
    assert exit_info.value.code == expected_code, "a missing command must exit with 2"


def test_missing_command_prints_the_usage(capsys: pytest.CaptureFixture[str]) -> None:
    arguments: list[str] = []
    with pytest.raises(SystemExit):
        cli.main(arguments)
    usage_word = "usage"
    assert usage_word in capsys.readouterr().err.lower(), "the usage was not printed"


@pytest.mark.usefixtures("home", "received_env_files")
def test_run_returns_zero() -> None:
    arguments = ["run", "--env-file", "prod.env"]
    assert cli.main(arguments) == 0, "run must succeed when the bot stops"


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (["run", "--env-file", "custom.env"], [Path("custom.env")]),
        (["run"], [None]),
    ],
    ids=["env-file", "default"],
)
@pytest.mark.usefixtures("home")
def test_run_starts_the_bot_with_the_env_file(
    received_env_files: list[Path | None],
    arguments: list[str],
    expected: list[Path | None],
) -> None:
    cli.main(arguments)
    assert received_env_files == expected, "the bot got a wrong env file"


@pytest.mark.usefixtures("home", "failing_bot")
def test_run_exits_with_a_usage_error_code_on_configuration_errors() -> None:
    arguments = ["run"]
    expected_code = 2
    with pytest.raises(SystemExit) as exit_info:
        cli.main(arguments)
    assert exit_info.value.code == expected_code, "a config error must exit with 2"


@pytest.mark.usefixtures("home", "failing_bot")
def test_run_names_the_broken_setting(capsys: pytest.CaptureFixture[str]) -> None:
    arguments = ["run", "--env-file", "broken.env"]
    with pytest.raises(SystemExit):
        cli.main(arguments)
    setting_name = "SUPERVISOR_ID"
    assert setting_name in capsys.readouterr().err, "the broken setting is not named"


def test_python_dash_m_exits_with_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    installed = "1.2.3"
    monkeypatch.setattr(cli, "package_version", lambda _name: installed)
    monkeypatch.setattr(sys, "argv", ["bot_obormot", "version"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("bot_obormot", run_name="__main__")
    assert exit_info.value.code == 0, "python -m bot_obormot version must exit with 0"


def test_python_dash_m_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    installed = "2.71.8"
    monkeypatch.setattr(cli, "package_version", lambda _name: installed)
    monkeypatch.setattr(sys, "argv", ["bot_obormot", "version"])
    with pytest.raises(SystemExit):
        runpy.run_module("bot_obormot", run_name="__main__")
    version_line = "bot-obormot 2.71.8"
    assert version_line in capsys.readouterr().out, "the module did not run the CLI"


@pytest.mark.usefixtures("home")
def test_config_check_fails_on_the_template(env_example: Path) -> None:
    arguments = ["config", "check", "--env-file", str(env_example)]
    expected_code = 1
    actual = cli.main(arguments)
    assert actual == expected_code, "the template must fail the config check"


@pytest.mark.parametrize(
    "expected_text",
    ["Configuration has problems:", "SUPERVISOR_ID", "BOT_TOKEN"],
    ids=["header", "supervisor", "bot-setting"],
)
@pytest.mark.usefixtures("home")
def test_config_check_shows_template_placeholder_errors(
    capsys: pytest.CaptureFixture[str], env_example: Path, expected_text: str
) -> None:
    cli.main(["config", "check", "--env-file", str(env_example)])
    output = capsys.readouterr().out
    assert expected_text in output, "the template problem report is incomplete"


@pytest.mark.usefixtures("home")
def test_config_check_hides_the_template_placeholder(
    capsys: pytest.CaptureFixture[str], env_example: Path
) -> None:
    cli.main(["config", "check", "--env-file", str(env_example)])
    supervisor_placeholder = "REPLACE_WITH_NUMERIC_TELEGRAM_ID"
    output = capsys.readouterr().out
    assert supervisor_placeholder not in output, "the placeholder value was printed"


@pytest.mark.usefixtures("home")
def test_config_check_fails_on_a_broken_environment() -> None:
    bot_key = "555666777:" + "Zq" * 18
    cli.os.environ.update(
        {"BOT_TOKEN": bot_key, "SUPERVISOR_ID": "hidden-id", "LLM_TIMEOUT": "0"}
    )
    expected_code = 1
    actual = cli.main(["config", "check"])
    assert actual == expected_code, "a broken environment must fail the check"


@pytest.mark.usefixtures("home")
def test_config_check_names_the_broken_setting(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bot_key = "246813579:" + "Kp_" * 11
    cli.os.environ.update(
        {"BOT_TOKEN": bot_key, "SUPERVISOR_ID": "classified", "LLM_TIMEOUT": "0"}
    )
    cli.main(["config", "check"])
    setting_name = "SUPERVISOR_ID"
    assert setting_name in capsys.readouterr().out, "the broken setting is not named"


@pytest.mark.usefixtures("home")
def test_config_check_never_prints_the_invalid_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bot_key = "123456789:" + "A" * 35
    leaked_value = "top-secret"
    cli.os.environ.update(
        {"BOT_TOKEN": bot_key, "SUPERVISOR_ID": leaked_value, "LLM_TIMEOUT": "0"}
    )
    cli.main(["config", "check"])
    output = capsys.readouterr().out
    assert leaked_value not in output, "an invalid setting value was printed"


@pytest.mark.usefixtures("home")
def test_config_check_never_prints_the_bot_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bot_key = "987654321:" + "xY-9" * 9
    cli.os.environ.update(
        {"BOT_TOKEN": bot_key, "SUPERVISOR_ID": "not-a-number", "LLM_TIMEOUT": "0"}
    )
    cli.main(["config", "check"])
    output = capsys.readouterr().out
    assert bot_key not in output, "the bot token was printed"


def test_config_check_accepts_a_valid_configuration(home: Path) -> None:
    bot_key = "123456789:" + "A" * 35
    home.mkdir()
    (home / ".env").write_text(
        f"BOT_TOKEN={bot_key}\nSUPERVISOR_ID=42\n", encoding="utf-8"
    )
    actual = cli.main(["config", "check"])
    assert actual == 0, "a valid configuration must pass the check"


def test_config_check_reports_a_valid_configuration(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    bot_key = "31415926:" + "b7" * 20
    home.mkdir()
    (home / ".env").write_text(
        f"BOT_TOKEN={bot_key}\nSUPERVISOR_ID=1009\n", encoding="utf-8"
    )
    cli.main(["config", "check"])
    expected_out = "Configuration is valid.\n"
    assert capsys.readouterr().out == expected_out, "the success line is wrong"


@pytest.mark.usefixtures("home")
def test_init_returns_zero() -> None:
    bot_key = "123456789:" + "A" * 35
    actual = cli.main(["init", "--token", bot_key, "--supervisor", "7"])
    assert actual == 0, "init must succeed"


def test_init_creates_a_private_file(home: Path) -> None:
    bot_key = "800500300:" + "Qw" * 16
    cli.main(["init", "--token", bot_key, "--supervisor", "64"])
    expected_mode = 0o600
    actual = (home / ".env").stat().st_mode & 0o777
    assert actual == expected_mode, "the configuration file is not private"


def test_init_writes_the_supervisor(home: Path) -> None:
    bot_key = "11223344:" + "Mn0" * 11
    cli.main(["init", "--token", bot_key, "--supervisor", "7"])
    supervisor_line = "SUPERVISOR_ID=7"
    content = (home / ".env").read_text(encoding="utf-8")
    assert supervisor_line in content, "the supervisor was not written"


def test_init_prints_the_created_path(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    bot_key = "90817263:" + "rT" * 17
    cli.main(["init", "--token", bot_key, "--supervisor", "305"])
    expected_line = f"Created configuration: {home / '.env'}"
    assert expected_line in capsys.readouterr().out, "the created path is not printed"


@pytest.mark.parametrize("step", ["  1. ", "  2. ", "  3. "])
@pytest.mark.usefixtures("home")
def test_init_prints_next_steps(capsys: pytest.CaptureFixture[str], step: str) -> None:
    bot_key = "123456789:" + "A" * 35
    cli.main(["init", "--token", bot_key, "--supervisor", "7"])
    assert step in capsys.readouterr().out, "a next step is missing"


def test_init_without_force_exits_with_a_usage_error_code(home: Path) -> None:
    home.mkdir()
    (home / ".env").write_text("OLD=1\n", encoding="utf-8")
    expected_code = 2
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["init"])
    assert exit_info.value.code == expected_code, "overwriting must exit with 2"


def test_init_without_force_names_the_force_option(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    home.mkdir()
    (home / ".env").write_text("KEEP_ME=yes\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["init"])
    force_option = "--force"
    assert force_option in capsys.readouterr().err, "the error must suggest --force"


def test_init_without_force_keeps_the_file(home: Path) -> None:
    home.mkdir()
    existing = "OLD=1\n"
    (home / ".env").write_text(existing, encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["init"])
    content = (home / ".env").read_text(encoding="utf-8")
    assert content == existing, "the existing file was changed"


def test_init_with_force_returns_zero(home: Path) -> None:
    home.mkdir()
    (home / ".env").write_text("LEGACY=2\n", encoding="utf-8")
    actual = cli.main(["init", "--force"])
    assert actual == 0, "init --force must succeed"


def test_init_with_force_overwrites_the_file(home: Path) -> None:
    home.mkdir()
    old_line = "OLD=1"
    (home / ".env").write_text(f"{old_line}\n", encoding="utf-8")
    cli.main(["init", "--force"])
    content = (home / ".env").read_text(encoding="utf-8")
    assert old_line not in content, "the old file was not overwritten"


@pytest.mark.usefixtures("home")
def test_init_rejects_an_invalid_token_with_a_usage_error_code() -> None:
    bot_key = "bad"
    expected_code = 2
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["init", "--token", bot_key])
    assert exit_info.value.code == expected_code, "an invalid token must exit with 2"


@pytest.mark.usefixtures("home")
def test_init_rejects_an_invalid_token_with_a_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    bot_key = "12:short"
    with pytest.raises(SystemExit):
        cli.main(["init", "--token", bot_key])
    bot_credential_word = "token"
    assert bot_credential_word in capsys.readouterr().err, "the token is not named"


def test_init_rejects_an_invalid_token_without_a_file(home: Path) -> None:
    bot_key = "no-colon-here"
    with pytest.raises(SystemExit):
        cli.main(["init", "--token", bot_key])
    created = (home / ".env").exists()
    assert created is False, "an invalid token still created the file"


@pytest.mark.usefixtures("home", "offline_values")
def test_doctor_fails_on_a_failed_check() -> None:
    expected_code = 1
    actual = cli.main(["doctor", "--offline"])
    assert actual == expected_code, "a failed check must fail doctor"


@pytest.mark.usefixtures("home")
def test_doctor_passes_the_offline_flag(offline_values: list[bool]) -> None:
    cli.main(["doctor", "--offline"])
    expected = [True]
    assert offline_values == expected, "doctor did not pass --offline on"


@pytest.mark.usefixtures("home", "offline_values")
def test_doctor_prints_all_lines(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["doctor", "--offline"])
    expected_lines = [
        "OK   Python: fine",
        "WARN ffmpeg: missing",
        "FAIL Settings: broken",
    ]
    actual = capsys.readouterr().out.splitlines()
    assert actual == expected_lines, "doctor printed wrong lines"


@pytest.mark.usefixtures("home", "quiet_checks")
def test_doctor_quiet_succeeds_without_failures() -> None:
    actual = cli.main(["doctor", "--quiet"])
    assert actual == 0, "doctor without failures must succeed"


@pytest.mark.usefixtures("home", "quiet_checks")
def test_doctor_quiet_hides_ok_lines(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["doctor", "--quiet"])
    expected_out = "WARN ffmpeg: missing\n"
    assert capsys.readouterr().out == expected_out, "quiet doctor printed OK lines"


@pytest.mark.usefixtures("home")
def test_service_install_print_only_returns_zero() -> None:
    actual = cli.main(["service", "install", "--print"])
    assert actual == 0, "printing the unit must succeed"


def test_service_install_print_only_prints_the_command(
    capsys: pytest.CaptureFixture[str], home: Path
) -> None:
    cli.main(["service", "install", "--print"])
    expected_line = f'ExecStart="{home}/.venv/bin/bot-obormot" run'
    assert expected_line in capsys.readouterr().out, "the unit runs a wrong command"


@pytest.mark.usefixtures("home")
def test_service_install_print_only_sets_the_home_variable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.main(["service", "install", "--print"])
    home_variable = "BOT_OBORMOT_HOME"
    assert home_variable in capsys.readouterr().out, "the unit misses the home"


def test_service_install_print_only_writes_nothing(home: Path) -> None:
    cli.main(["service", "install", "--print"])
    created = (home / ".config").exists()
    assert created is False, "printing the unit wrote files"


@pytest.mark.usefixtures("home", "user_home")
def test_service_install_returns_zero() -> None:
    actual = cli.main(["service", "install"])
    assert actual == 0, "installing the unit must succeed"


@pytest.mark.usefixtures("home")
def test_service_install_writes_the_user_unit(user_home: Path) -> None:
    cli.main(["service", "install"])
    unit = user_home / ".config" / "systemd" / "user" / "bot-obormot.service"
    assert unit.is_file(), "the user unit was not written"


@pytest.mark.parametrize(
    "expected_text",
    [
        "was not enabled or started",
        "systemctl --user daemon-reload",
        "systemctl --user enable --now bot-obormot.service",
    ],
    ids=["note", "reload", "enable"],
)
@pytest.mark.usefixtures("home", "user_home")
def test_service_install_prints_commands(
    capsys: pytest.CaptureFixture[str], expected_text: str
) -> None:
    cli.main(["service", "install"])
    assert expected_text in capsys.readouterr().out, "an install hint is missing"


@pytest.mark.usefixtures("home", "user_home")
def test_service_install_refuses_an_existing_unit() -> None:
    cli.main(["service", "install"])
    expected_code = 2
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["service", "install"])
    assert exit_info.value.code == expected_code, "a second install must exit with 2"


@pytest.mark.usefixtures("home", "user_home")
def test_service_uninstall_without_a_unit_returns_zero() -> None:
    actual = cli.main(["service", "uninstall"])
    assert actual == 0, "uninstalling a missing unit must succeed"


@pytest.mark.usefixtures("home", "user_home")
def test_service_uninstall_without_a_unit_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.main(["service", "uninstall"])
    no_unit_note = "No systemd unit is installed."
    assert no_unit_note in capsys.readouterr().out, "the missing unit is not reported"


@pytest.mark.usefixtures("home", "user_home")
def test_service_uninstall_removes_the_unit_and_returns_zero() -> None:
    cli.main(["service", "install"])
    actual = cli.main(["service", "uninstall"])
    assert actual == 0, "uninstalling the unit must succeed"


@pytest.mark.parametrize(
    "expected_text",
    ["was not stopped", "disable --now bot-obormot.service"],
    ids=["note", "disable"],
)
@pytest.mark.usefixtures("home", "user_home")
def test_service_uninstall_prints_commands(
    capsys: pytest.CaptureFixture[str], expected_text: str
) -> None:
    cli.main(["service", "install"])
    capsys.readouterr()
    cli.main(["service", "uninstall"])
    assert expected_text in capsys.readouterr().out, "an uninstall hint is missing"


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
