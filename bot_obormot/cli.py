# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Command-line interface of bot-obormot."""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from importlib.metadata import version as package_version
from pathlib import Path

from bot_obormot.app.bootstrap import main as run_bot
from bot_obormot.doctor import (
    FAIL_STATUS,
    OK_STATUS,
    DiagnosticCheck,
    check_bot_token,
    collect_doctor_checks,
)
from bot_obormot.env_readers import get_home_dir, load_env_file
from bot_obormot.initial_env import write_initial_env
from bot_obormot.service import (
    UNIT_NAME,
    USER_MODE,
    ServiceMode,
    install_service_unit,
    render_service_unit,
    uninstall_service_unit,
)
from bot_obormot.settings import ConfigError, load_settings

CONFIG_CHECK_COMMAND = "check"
SERVICE_INSTALL_COMMAND = "install"
SERVICE_UNINSTALL_COMMAND = "uninstall"

CommandHandler = Callable[[argparse.Namespace, argparse.ArgumentParser], int]


def _positive_int(value: str) -> int:
    """Parse a positive integer argument."""
    try:
        number = int(value)
    except ValueError as error:
        message = "Value must be an integer."
        raise argparse.ArgumentTypeError(message) from error
    if number <= 0:
        message = "Value must be a positive integer."
        raise argparse.ArgumentTypeError(message)
    return number


def _add_mode_arguments(parser: argparse.ArgumentParser) -> None:
    """Add the mutually exclusive --user/--system options."""
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--user", dest="service_mode", action="store_const", const="user"
    )
    group.add_argument(
        "--system", dest="service_mode", action="store_const", const="system"
    )
    parser.set_defaults(service_mode="user")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(prog="bot-obormot")
    commands = parser.add_subparsers(dest="command", required=True)

    run_parser = commands.add_parser("run", help="Run the Telegram bot.")
    run_parser.add_argument("--env-file", type=Path)

    commands.add_parser("version", help="Show the installed version.")

    config_parser = commands.add_parser("config", help="Inspect the configuration.")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    check_parser = config_commands.add_parser("check", help="Validate the settings.")
    check_parser.add_argument("--env-file", type=Path)

    init_parser = commands.add_parser("init", help="Create a protected .env file.")
    init_parser.add_argument("--token")
    init_parser.add_argument("--supervisor", type=_positive_int)
    init_parser.add_argument("--force", action="store_true")

    doctor_parser = commands.add_parser("doctor", help="Check the installation.")
    doctor_parser.add_argument(
        "--offline", action="store_true", help="Skip network checks."
    )
    doctor_parser.add_argument(
        "--quiet", action="store_true", help="Print only warnings and failures."
    )

    service_parser = commands.add_parser("service", help="Manage the systemd unit.")
    service_commands = service_parser.add_subparsers(
        dest="service_command", required=True
    )
    install_parser = service_commands.add_parser(
        "install", help="Render or install a systemd unit."
    )
    _add_mode_arguments(install_parser)
    install_parser.add_argument("--print", dest="print_unit", action="store_true")
    install_parser.add_argument("--force", action="store_true")
    uninstall_parser = service_commands.add_parser(
        "uninstall", help="Remove the systemd unit file."
    )
    _add_mode_arguments(uninstall_parser)
    status_parser = service_commands.add_parser(
        "status", help="Show the service status."
    )
    _add_mode_arguments(status_parser)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the bot-obormot command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)

    handlers: dict[str, CommandHandler] = {
        "run": _handle_run,
        "version": _handle_version,
        "config": _handle_config,
        "init": _handle_init,
        "doctor": _handle_doctor,
        "service": _handle_service,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_usage(sys.stderr)
        sys.stderr.write(f"{parser.prog}: error: Unsupported command.\n")
        return 2
    return handler(args, parser)


def _handle_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Run the bot until it is stopped."""
    try:
        _run_until_stopped(args.env_file)
    except ConfigError as error:
        parser.error(str(error))
    return 0


def _run_until_stopped(env_file: Path | None) -> None:
    """Run the bot and treat an interrupt or exit request as a normal stop."""
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(run_bot(env_file))


def _handle_version(_args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    """Print the installed package version."""
    sys.stdout.write(f"bot-obormot {package_version('bot-obormot')}\n")
    return 0


def configuration_problems(environ: Mapping[str, str]) -> list[str]:
    """Collect configuration problems without exposing secret values."""
    problems: list[str] = []
    try:
        load_settings(environ)
    except ConfigError as error:
        problems.extend(message.partition(" Got:")[0] for message in error.errors)

    token_check = check_bot_token(environ)
    if token_check.status == FAIL_STATUS:
        problems.append(token_check.message)
    return problems


def _handle_config(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    """Handle ``config check``."""
    if args.config_command != CONFIG_CHECK_COMMAND:
        return 2
    load_env_file(args.env_file)
    problems = configuration_problems(os.environ)
    if problems:
        sys.stdout.write("Configuration has problems:\n")
        for problem in problems:
            sys.stdout.write(f"- {problem}\n")
        return 1
    sys.stdout.write("Configuration is valid.\n")
    return 0


def _handle_init(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Create the protected .env file and print the next steps."""
    try:
        env_path = write_initial_env(
            get_home_dir(),
            token=args.token,
            supervisor=args.supervisor,
            force=args.force,
        )
    except FileExistsError:
        parser.error("Configuration already exists. Use --force to overwrite.")
    except (OSError, ValueError) as error:
        parser.error(str(error))

    sys.stdout.write(f"Created configuration: {env_path}\n")
    sys.stdout.write("Next steps:\n")
    sys.stdout.write(
        f"  1. Edit {env_path}: set BOT_TOKEN, SUPERVISOR_ID and the LLM server.\n"
    )
    sys.stdout.write("  2. Check the installation: bot-obormot doctor\n")
    sys.stdout.write(
        "  3. Start the bot: bot-obormot run "
        "(or run 'bot-obormot service install' to use systemd)\n"
    )
    return 0


def _format_check(check: DiagnosticCheck) -> str:
    """Format one diagnostic result as a line of output."""
    return f"{check.status:4} {check.name}: {check.message}\n"


def _handle_doctor(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> int:
    """Print the installation diagnostics and fail on any FAIL result."""
    load_env_file()
    checks = collect_doctor_checks(os.environ, offline=args.offline)
    for check in checks:
        if args.quiet and check.status == OK_STATUS:
            continue
        sys.stdout.write(_format_check(check))
    return 1 if any(check.status == FAIL_STATUS for check in checks) else 0


def _systemctl_commands(mode: ServiceMode, *actions: str) -> tuple[str, ...]:
    """Return the exact systemctl commands to print for the user to run."""
    prefix = "systemctl --user" if mode == USER_MODE else "sudo systemctl"
    return tuple(f"{prefix} {action}" for action in actions)


def _handle_service(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Handle systemd unit management; never start or stop the service."""
    mode: ServiceMode = args.service_mode
    home = get_home_dir()
    try:
        return _run_service_command(args, home, mode)
    except (OSError, ValueError) as error:
        return parser.error(str(error))


def _run_service_command(
    args: argparse.Namespace, home: Path, mode: ServiceMode
) -> int:
    """Run the selected ``service`` subcommand."""
    if args.service_command == SERVICE_INSTALL_COMMAND:
        return _service_install(args, home, mode)
    if args.service_command == SERVICE_UNINSTALL_COMMAND:
        return _service_uninstall(mode)
    return _service_status(mode)


def _service_install(args: argparse.Namespace, home: Path, mode: ServiceMode) -> int:
    """Print or install the unit and show the next commands."""
    if args.print_unit:
        sys.stdout.write(render_service_unit(home, mode=mode))
        return 0
    unit_path = install_service_unit(home, mode=mode, force=args.force)
    sys.stdout.write(f"Installed {mode} systemd unit: {unit_path}\n")
    sys.stdout.write("The service was not enabled or started. When ready, run:\n")
    for command in _systemctl_commands(
        mode, "daemon-reload", f"enable --now {UNIT_NAME}", f"status {UNIT_NAME}"
    ):
        sys.stdout.write(f"  {command}\n")
    return 0


def _service_uninstall(mode: ServiceMode) -> int:
    """Remove the unit file and show how to stop the service."""
    removed = uninstall_service_unit(mode=mode)
    if removed is None:
        sys.stdout.write("No systemd unit is installed.\n")
        return 0
    sys.stdout.write(f"Removed {mode} systemd unit: {removed}\n")
    sys.stdout.write("The service was not stopped. If it is running, run:\n")
    for command in _systemctl_commands(
        mode, f"disable --now {UNIT_NAME}", "daemon-reload"
    ):
        sys.stdout.write(f"  {command}\n")
    return 0


def _service_status(mode: ServiceMode) -> int:
    """Show the read-only systemctl status of the service."""
    systemctl = shutil.which("systemctl")
    if systemctl is None:
        message = "systemctl was not found on this system."
        raise OSError(message)
    command = [systemctl]
    if mode == USER_MODE:
        command.append("--user")
    command.extend(("status", "--no-pager", UNIT_NAME))
    return subprocess.run(command, check=False).returncode  # noqa: S603 - fixed argv; shell=False.
