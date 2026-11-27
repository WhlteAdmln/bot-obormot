# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for the POSIX release wheel installer (real flow in a temporary HOME)."""

import base64
import csv
import functools
import hashlib
import http.server
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import Literal

import pytest

from tests.support.fake_mv import create_mv_stub

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INSTALLER = PROJECT_ROOT / "install.sh"

FAKE_CLI_SOURCE = """
import json
import os
import sys
from pathlib import Path


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    home = Path(os.environ["BOT_OBORMOT_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    with (home / "calls.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(args) + "\\n")

    if args[0] == "init":
        env_path = home / ".env"
        env_path.write_text("BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN\\n", encoding="utf-8")
        env_path.chmod(0o600)
        return 0

    if args[0] == "doctor":
        if os.environ.get("FAKE_DOCTOR_FAIL") == "1":
            print("FAIL forced doctor failure.")
            return 1
        if "--offline" in args and os.environ.get("FAKE_DOCTOR_FAIL_OFFLINE") == "1":
            print("FAIL Settings: forced offline failure.")
            return 1
        print("doctor OK")
        return 0

    if args[:2] == ["service", "install"]:
        if "--print" in args:
            sys.stdout.write(
                "[Service]\\n"
                f'ExecStart="{home}/.venv/bin/bot-obormot" run\\n'
            )
            return 0
        (home / "service-installed").write_text("ok", encoding="utf-8")
        return 0

    if args[0] == "run":
        return 0

    return 2
"""


def run_installer(
    *arguments: str,
    release_url: str | None = None,
    home: Path | None = None,
    app_home: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the installer with an isolated environment."""
    shell_path = shutil.which("sh")
    if shell_path is None:
        message = "A POSIX shell is required."
        raise RuntimeError(message)

    environment = os.environ.copy()
    environment["PIP_NO_INDEX"] = "1"
    environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    for name in (
        "BOT_OBORMOT_HOME",
        "BOT_OBORMOT_RELEASE_URL",
        "BOT_OBORMOT_RELEASE_TAG",
        "BOT_OBORMOT_GITHUB_REPOSITORY",
        "GITHUB_TOKEN",
    ):
        environment.pop(name, None)

    if home is not None:
        environment["HOME"] = str(home)
    if app_home is not None:
        environment["BOT_OBORMOT_HOME"] = str(app_home)
    if release_url is not None:
        environment["BOT_OBORMOT_RELEASE_URL"] = release_url
        environment["BOT_OBORMOT_RELEASE_TAG"] = "local"
    if extra_env is not None:
        environment.update(extra_env)

    upgrade_option = "--upgrade"
    return subprocess.run(  # noqa: S603 - resolved shell runs the local installer.
        [shell_path, str(INSTALLER), *arguments],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=600 if upgrade_option in arguments else 120,
    )


def output_of(result: subprocess.CompletedProcess[str]) -> str:
    """Return both output streams of an installer run for a failure message."""
    return f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def calls_of(app_home: Path) -> list[list[str]]:
    """Return the commands recorded by the fake CLI."""
    path = app_home / "calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def installed_version(app_home: Path) -> str:
    """Return the installed bot-obormot version, or an empty string."""
    metadata_files = list(
        (app_home / ".venv").glob(
            "lib/python*/site-packages/bot_obormot-*.dist-info/METADATA"
        )
    )
    if len(metadata_files) != 1:
        return ""
    for line in metadata_files[0].read_text(encoding="utf-8").splitlines():
        if line.startswith("Version: "):
            return line.removeprefix("Version: ")
    return ""


def mode_of(path: Path) -> int:
    """Return the permission bits of a file."""
    return path.stat().st_mode & 0o777


def create_systemctl_stub(tmp_path: Path, *, active: bool) -> tuple[Path, Path]:
    """Create a systemctl stub that reports service state and records calls."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    log_path = tmp_path / "systemctl.log"
    status = 0 if active else 3
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$FAKE_SYSTEMCTL_LOG"\n'
        f'if [ "$2" = "is-active" ]; then exit {status}; fi\n'
        'if [ "$2" = "daemon-reload" ]; then exit 0; fi\n'
        "exit 1\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    return fake_bin, log_path


def systemctl_environment(fake_bin: Path, log_path: Path) -> dict[str, str]:
    """Build the environment that puts the systemctl stub first in PATH."""
    return {
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
        "FAKE_SYSTEMCTL_LOG": str(log_path),
    }


def create_test_wheel(release_dir: Path, *, version: str = "1.2.3") -> Path:
    """Build a minimal wheel with an isolated fake CLI."""
    distribution = f"bot_obormot-{version}.dist-info"
    wheel_name = f"bot_obormot-{version}-py3-none-any.whl"

    files = {
        "bot_obormot/__init__.py": b"",
        "bot_obormot/__main__.py": (
            b"import sys\nfrom bot_obormot.cli import main\nsys.exit(main())\n"
        ),
        "bot_obormot/cli.py": FAKE_CLI_SOURCE.encode("utf-8"),
        f"{distribution}/METADATA": (
            "Metadata-Version: 2.1\n"
            "Name: bot-obormot\n"
            f"Version: {version}\n"
            "Requires-Python: >=3.11\n"
            "Provides-Extra: tgs\n\n"
        ).encode(),
        f"{distribution}/WHEEL": (
            b"Wheel-Version: 1.0\n"
            b"Generator: bot-obormot-installer-test\n"
            b"Root-Is-Purelib: true\n"
            b"Tag: py3-none-any\n"
        ),
        f"{distribution}/entry_points.txt": (
            b"[console_scripts]\nbot-obormot = bot_obormot.cli:main\n"
        ),
    }

    rows = []
    for name, content in files.items():
        digest = (
            base64.urlsafe_b64encode(hashlib.sha256(content).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        rows.append((name, f"sha256={digest}", str(len(content))))

    record_name = f"{distribution}/RECORD"
    record_stream = io.StringIO()
    csv.writer(record_stream, lineterminator="\n").writerows(
        [*rows, (record_name, "", "")]
    )
    files[record_name] = record_stream.getvalue().encode("utf-8")

    wheel_path = release_dir / wheel_name
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)

    return wheel_path


def write_checksums(
    release_dir: Path,
    wheel_path: Path | None,
    *,
    corrupt: bool = False,
) -> None:
    """Write a release checksum manifest; ``None`` models a release without wheel."""
    archive_digest = hashlib.sha256(b"release-archive").hexdigest()
    lines = [f"{archive_digest}  bot-obormot-1.2.3.zip"]
    if wheel_path is not None:
        wheel_digest = "0" * 64 if corrupt else sha256_of(wheel_path)
        lines.append(f"{wheel_digest}  {wheel_path.name}")
    constraints = (release_dir / "constraints.txt").read_bytes()
    lines.append(f"{hashlib.sha256(constraints).hexdigest()}  constraints.txt")
    (release_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture(name="local_release")
def fixture_local_release(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Provide release assets through a local HTTP server."""
    release_dir = tmp_path / "release"
    release_dir.mkdir()

    wheel_path = create_test_wheel(release_dir)
    (release_dir / "constraints.txt").write_text("", encoding="utf-8")
    write_checksums(release_dir, wheel_path)

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(
            http.server.SimpleHTTPRequestHandler,
            directory=str(release_dir),
        ),
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", release_dir
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


@pytest.fixture(name="user_home")
def fixture_user_home(tmp_path: Path) -> Path:
    """Create an isolated user home directory."""
    path = tmp_path / "user"
    path.mkdir()
    return path


def install_version_one(
    release_url: str, user_home: Path, *extra: str, env: dict[str, str] | None = None
) -> Path:
    """Install the first fake release and return the application home."""
    result = run_installer(
        *extra, release_url=release_url, home=user_home, extra_env=env
    )
    app_home = user_home / "bot-obormot"
    first_version = "1.2.3"
    if result.returncode != 0 or installed_version(app_home) != first_version:
        message = f"The first installation failed.\n{output_of(result)}"
        raise RuntimeError(message)
    return app_home


def publish_version_two(release_dir: Path) -> None:
    """Publish a second fake release over the first one."""
    write_checksums(release_dir, create_test_wheel(release_dir, version="2.0.0"))


def sha256_of(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_help_lists_every_option() -> None:
    result = run_installer("--help")
    flags = ("--version", "--nightly", "--systemd", "--with-tgs", "--upgrade")
    observed = (
        result.returncode,
        [flag for flag in flags if flag not in result.stdout],
    )
    expected = (0, [])
    assert observed == expected, f"help misses options\n{output_of(result)}"


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--version", "v1.O.0"), "Invalid version: v1.O.0"),
        (("--version", "1.0.0;id"), "Invalid version: 1.0.0;id"),
        (("--version", "../1.0.0"), "Invalid version: ../1.0.0"),
        (("--version", "1.0.0 rc"), "Invalid version: 1.0.0 rc"),
        (("--version", "1.0.0/../../x"), "Invalid version"),
        (("--version", "-x"), "Invalid value for --version: -x"),
        (("--version", ""), "Invalid value for --version"),
        (("--version", "1.0.0", "--nightly"), "only one of"),
        (("--upgrade", "--systemd"), "never touches the systemd unit"),
        (("--unknown",), "Unknown argument"),
        (("--version",), "requires a value"),
    ],
    ids=[
        "word",
        "command-separator",
        "path-traversal",
        "space",
        "slash",
        "option-as-value",
        "empty",
        "version-and-nightly",
        "upgrade-and-systemd",
        "unknown",
        "missing-value",
    ],
)
def test_invalid_arguments_fail_before_any_installation(
    arguments: tuple[str, ...], message: str, user_home: Path
) -> None:
    result = run_installer(*arguments, home=user_home)
    observed = (
        result.returncode != 0,
        message in result.stderr,
        (user_home / "bot-obormot").exists(),
    )
    expected = (True, True, False)
    assert observed == expected, f"the arguments must be refused\n{output_of(result)}"


@pytest.mark.parametrize(
    ("repository", "message"),
    [
        ("owner/name/extra", "Invalid GitHub repository"),
        ("/name", "Invalid GitHub repository"),
        ("owner/", "Invalid GitHub repository"),
        ("owner/na me", "Invalid GitHub repository"),
        ("owner/name?x=1", "Invalid GitHub repository"),
        ("owner", "must have owner/name format"),
    ],
    ids=["three-parts", "no-owner", "no-name", "space", "query", "no-slash"],
)
def test_invalid_repository_fails_before_any_installation(
    repository: str, message: str, user_home: Path
) -> None:
    result = run_installer(
        home=user_home, extra_env={"BOT_OBORMOT_GITHUB_REPOSITORY": repository}
    )
    observed = (result.returncode != 0, message in result.stderr)
    expected = (True, True)
    assert observed == expected, f"the repository must be refused\n{output_of(result)}"


@pytest.mark.parametrize(
    "relative_home",
    ["/", "<home>", "<home>/", "<home>//"],
    ids=["root", "home", "home-slash", "home-double-slash"],
)
def test_unsafe_installation_directory_is_refused(
    relative_home: str, user_home: Path
) -> None:
    app_home = relative_home.replace("<home>", str(user_home))
    result = run_installer(home=user_home, extra_env={"BOT_OBORMOT_HOME": app_home})
    unsafe_error = "Refusing unsafe installation directory"
    observed = (
        result.returncode != 0,
        unsafe_error in result.stderr,
    )
    expected = (True, True)
    assert observed == expected, f"the directory must be refused\n{output_of(result)}"


@pytest.mark.parametrize(
    "tag",
    ["v1.0.0;id", "v1/../../x", "v1 0", "$(id)"],
    ids=["command-separator", "path-traversal", "space", "substitution"],
)
def test_invalid_release_tag_is_refused_before_download(
    tag: str, user_home: Path
) -> None:
    result = run_installer(
        release_url="http://127.0.0.1:9",
        home=user_home,
        extra_env={"BOT_OBORMOT_RELEASE_TAG": tag},
    )
    observed = (
        result.returncode != 0,
        f"Invalid release tag: {tag}" in result.stderr,
        (user_home / "bot-obormot").exists(),
    )
    expected = (True, True, False)
    assert observed == expected, f"the tag must be refused\n{output_of(result)}"


def test_fresh_install_runs_init_doctor_and_systemd(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release
    app_home = user_home / "custom home"
    result = run_installer(
        "--systemd", release_url=release_url, home=user_home, app_home=app_home
    )
    manual_start_note = "does not enable or start"
    observed = {
        "exit code": result.returncode,
        "cli installed": (app_home / ".venv" / "bin" / "bot-obormot").is_file(),
        "env mode": oct(mode_of(app_home / ".env")),
        "service installed": (app_home / "service-installed").is_file(),
        "calls": calls_of(app_home),
        "manual start note": manual_start_note in result.stdout,
    }
    expected = {
        "exit code": 0,
        "cli installed": True,
        "env mode": oct(0o600),
        "service installed": True,
        "calls": [["init"], ["doctor", "--offline"], ["service", "install", "--user"]],
        "manual start note": True,
    }
    assert observed == expected, f"the fresh install is wrong\n{output_of(result)}"


def test_fresh_install_succeeds_when_doctor_reports_template_values(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release
    result = run_installer(
        release_url=release_url, home=user_home, extra_env={"FAKE_DOCTOR_FAIL": "1"}
    )
    doctor_warning = "doctor reported problems"
    observed = (
        result.returncode,
        doctor_warning in result.stdout,
        (user_home / "bot-obormot" / ".env").is_file(),
    )
    expected = (0, True, True)
    assert observed == expected, f"template values must only warn\n{output_of(result)}"


def test_with_tgs_installs_the_optional_extra(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release
    result = run_installer("--with-tgs", release_url=release_url, home=user_home)
    observed = (result.returncode, installed_version(user_home / "bot-obormot"))
    expected = (0, "1.2.3")
    assert observed == expected, f"the extra must install\n{output_of(result)}"


def test_checksum_mismatch_stops_the_installation(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    wheel_path = next(release_dir.glob("bot_obormot-*.whl"))
    write_checksums(release_dir, wheel_path, corrupt=True)
    result = run_installer(release_url=release_url, home=user_home)
    checksum_error = "SHA-256 verification failed"
    observed = (
        result.returncode != 0,
        checksum_error in result.stderr,
        (user_home / "bot-obormot").exists(),
    )
    expected = (True, True, False)
    assert observed == expected, f"a bad checksum must stop\n{output_of(result)}"


def test_tampered_wheel_stops_the_installation(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    wheel_path = next(release_dir.glob("bot_obormot-*.whl"))
    with zipfile.ZipFile(wheel_path, "a") as archive:
        archive.writestr("bot_obormot/backdoor.py", "import os\n")
    result = run_installer(release_url=release_url, home=user_home)
    checksum_error = "SHA-256 verification failed"
    observed = (
        result.returncode != 0,
        checksum_error in result.stderr,
        (user_home / "bot-obormot").exists(),
    )
    expected = (True, True, False)
    assert observed == expected, f"a tampered wheel must stop\n{output_of(result)}"


def test_release_without_wheel_names_the_tag_and_installer_url(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    write_checksums(release_dir, None)
    result = run_installer(
        release_url=release_url,
        home=user_home,
        extra_env={"BOT_OBORMOT_RELEASE_TAG": "v0.1.1"},
    )
    missing_wheel_error = "v0.1.1 has no wheel asset"
    installer_path = "/v0.1.1/install.sh"
    observed = (
        result.returncode != 0,
        missing_wheel_error in result.stderr,
        installer_path in result.stderr,
        (user_home / "bot-obormot").exists(),
    )
    expected = (True, True, True, False)
    assert observed == expected, f"a release without wheel\n{output_of(result)}"


def test_existing_home_is_refused_without_upgrade(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release
    app_home = user_home / "bot-obormot"
    app_home.mkdir()
    marker = app_home / "keep.txt"
    marker.write_text("existing data", encoding="utf-8")
    result = run_installer(release_url=release_url, home=user_home)
    upgrade_hint = "Use --upgrade"
    observed = (
        result.returncode != 0,
        upgrade_hint in result.stderr,
        marker.read_text(encoding="utf-8"),
    )
    expected = (True, True, "existing data")
    assert observed == expected, f"an existing home must stay\n{output_of(result)}"


def test_upgrade_preserves_env_and_data_and_never_touches_the_unit(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    app_home = install_version_one(release_url, user_home)
    env_path = app_home / ".env"
    env_path.write_text("CUSTOM_SETTING=keep-me\n", encoding="utf-8")
    database = app_home / "data" / "bot.db"
    database.parent.mkdir()
    database.write_bytes(b"sqlite-data")
    env_hash, database_hash = sha256_of(env_path), sha256_of(database)
    old_marker = app_home / ".venv" / "old-environment-marker"
    old_marker.write_text("old", encoding="utf-8")
    publish_version_two(release_dir)
    result = run_installer("--upgrade", release_url=release_url, home=user_home)
    restart_command = "systemctl --user restart bot-obormot.service"
    observed = {
        "exit code": result.returncode,
        "env kept": sha256_of(env_path) == env_hash,
        "database kept": sha256_of(database) == database_hash,
        "old environment left": old_marker.exists(),
        "version": installed_version(app_home),
        "staged left": (app_home / ".venv.new").exists(),
        "backup left": (app_home / ".venv.prev").exists(),
        "restart hint": restart_command in result.stdout,
        "last call": calls_of(app_home)[-1],
        "unit touched": ["service", "install", "--user"] in calls_of(app_home),
    }
    expected = {
        "exit code": 0,
        "env kept": True,
        "database kept": True,
        "old environment left": False,
        "version": "2.0.0",
        "staged left": False,
        "backup left": False,
        "restart hint": True,
        "last call": ["doctor", "--offline"],
        "unit touched": False,
    }
    assert observed == expected, f"the upgrade is wrong\n{output_of(result)}"


def test_upgrade_leaves_no_staged_path_in_the_environment_files(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    app_home = install_version_one(release_url, user_home)
    publish_version_two(release_dir)
    result = run_installer("--upgrade", release_url=release_url, home=user_home)
    environment = app_home / ".venv"
    files = [
        path
        for path in (*(environment / "bin").iterdir(), environment / "pyvenv.cfg")
        if path.is_file() and not path.is_symlink()
    ]
    entry_point = subprocess.run(  # noqa: S603 - runs the CLI installed by the test.
        [str(environment / "bin" / "bot-obormot"), "doctor", "--offline"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "BOT_OBORMOT_HOME": str(app_home)},
        timeout=60,
    )
    interpreter = str(environment / "bin" / "python").encode()
    staged_marker = b".venv.new"
    observed = {
        "exit code": result.returncode,
        "entry point listed": environment / "bin" / "bot-obormot" in files,
        "staged paths": [
            path.name for path in files if staged_marker in path.read_bytes()
        ],
        "final interpreter": interpreter
        in (environment / "bin" / "bot-obormot").read_bytes(),
        "entry point exit code": entry_point.returncode,
    }
    expected = {
        "exit code": 0,
        "entry point listed": True,
        "staged paths": [],
        "final interpreter": True,
        "entry point exit code": 0,
    }
    assert observed == expected, f"staged paths remain\n{output_of(result)}"


def test_upgrade_keeps_the_old_version_when_offline_doctor_fails(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    app_home = install_version_one(release_url, user_home)
    old_marker = app_home / ".venv" / "old-environment-marker"
    old_marker.write_text("old", encoding="utf-8")
    publish_version_two(release_dir)
    result = run_installer(
        "--upgrade",
        release_url=release_url,
        home=user_home,
        extra_env={"FAKE_DOCTOR_FAIL_OFFLINE": "1"},
    )
    doctor_error = "doctor --offline failed"
    observed = {
        "failed": result.returncode != 0,
        "doctor error": doctor_error in result.stderr,
        "old marker": old_marker.read_text(encoding="utf-8"),
        "version": installed_version(app_home),
        "staged left": (app_home / ".venv.new").exists(),
        "backup left": (app_home / ".venv.prev").exists(),
    }
    expected = {
        "failed": True,
        "doctor error": True,
        "old marker": "old",
        "version": "1.2.3",
        "staged left": False,
        "backup left": False,
    }
    assert observed == expected, f"the old version must stay\n{output_of(result)}"


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("move", "Could not activate the staged virtual environment."),
        ("relocate", "Could not update the paths of the activated virtual"),
    ],
    ids=["move", "relocate"],
)
def test_upgrade_restores_the_previous_environment_when_the_switch_fails(
    tmp_path: Path,
    user_home: Path,
    local_release: tuple[str, Path],
    failure: Literal["move", "relocate"],
    message: str,
) -> None:
    release_url, release_dir = local_release
    app_home = install_version_one(release_url, user_home)
    old_marker = app_home / ".venv" / "old-environment-marker"
    old_marker.write_text("previous environment", encoding="utf-8")
    publish_version_two(release_dir)
    fake_bin = create_mv_stub(tmp_path / "mv-bin", failure)
    result = run_installer(
        "--upgrade",
        release_url=release_url,
        home=user_home,
        extra_env={"PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]},
    )
    restore_error = "Could not restore"
    observed = {
        "failed": result.returncode != 0,
        "switch error": message in result.stderr,
        "restore error": restore_error in result.stderr,
        "old marker": old_marker.read_text(encoding="utf-8"),
        "version": installed_version(app_home),
        "staged left": (app_home / ".venv.new").exists(),
        "backup left": (app_home / ".venv.prev").exists(),
    }
    expected = {
        "failed": True,
        "switch error": True,
        "restore error": False,
        "old marker": "previous environment",
        "version": "1.2.3",
        "staged left": False,
        "backup left": False,
    }
    assert observed == expected, f"the old environment must return\n{output_of(result)}"


def test_upgrade_refuses_while_the_user_service_is_active(
    tmp_path: Path, user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    app_home = install_version_one(release_url, user_home)
    publish_version_two(release_dir)
    fake_bin, log_path = create_systemctl_stub(tmp_path, active=True)
    result = run_installer(
        "--upgrade",
        release_url=release_url,
        home=user_home,
        extra_env=systemctl_environment(fake_bin, log_path),
    )
    active_note = "user service is active"
    observed = (
        result.returncode != 0,
        active_note in result.stderr,
        installed_version(app_home),
        (app_home / ".venv.new").exists(),
    )
    expected = (True, True, "1.2.3", False)
    assert observed == expected, f"an active service blocks\n{output_of(result)}"


def test_upgrade_refuses_a_symlinked_env_file(
    tmp_path: Path, user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    app_home = install_version_one(release_url, user_home)
    elsewhere = tmp_path / "elsewhere.env"
    elsewhere.write_text("BOT_TOKEN=elsewhere\n", encoding="utf-8")
    (app_home / ".env").unlink()
    (app_home / ".env").symlink_to(elsewhere)
    publish_version_two(release_dir)
    result = run_installer("--upgrade", release_url=release_url, home=user_home)
    env_error = "existing regular .env file"
    observed = (
        result.returncode != 0,
        env_error in result.stderr,
        installed_version(app_home),
    )
    expected = (True, True, "1.2.3")
    assert observed == expected, f"a symlinked .env must block\n{output_of(result)}"


def _embedded_snippets() -> list[str]:
    text = INSTALLER.read_text(encoding="utf-8")
    return re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", text, re.DOTALL)


def _syntax_errors(snippets: list[str]) -> list[str]:
    errors = []
    for number, snippet in enumerate(snippets):
        try:
            compile(snippet, f"<install.sh snippet {number}>", "exec")
        except SyntaxError as error:
            errors.append(str(error))
    return errors


def test_installer_embeds_two_python_snippets() -> None:
    expected = 2
    assert len(_embedded_snippets()) == expected, "install.sh must embed two snippets"


def test_embedded_python_snippets_compile() -> None:
    expected_empty: list[str] = []
    assert _syntax_errors(_embedded_snippets()) == expected_empty, (
        "an embedded snippet has a syntax error"
    )


def _release_info(tmp_path: Path, release: object) -> subprocess.CompletedProcess[str]:
    release_path = tmp_path / "release.json"
    release_path.write_text(json.dumps(release), encoding="utf-8")
    destination = tmp_path / "info.txt"
    return subprocess.run(  # noqa: S603 - runs the test interpreter on a local snippet.
        [sys.executable, "-", str(release_path), str(destination), "latest"],
        input=_embedded_snippets()[0],
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_snippet_reads_the_tag_and_wheel_count(tmp_path: Path) -> None:
    _release_info(
        tmp_path,
        {
            "tag_name": "v0.2.0",
            "draft": False,
            "assets": [{"name": "bot_obormot-0.2.0-py3-none-any.whl"}],
        },
    )
    lines = (tmp_path / "info.txt").read_text(encoding="utf-8").splitlines()
    expected = ["v0.2.0", "1"]
    assert lines == expected, "the snippet must write the tag and the wheel count"


@pytest.mark.parametrize(
    "tag",
    ["v0.2.0;id", "../v0.2.0", "", "v0.2.0\nINJECTED"],
    ids=["command-separator", "path-traversal", "empty", "line-break"],
)
def test_release_snippet_rejects_a_hostile_tag(tmp_path: Path, tag: str) -> None:
    result = _release_info(
        tmp_path,
        {"tag_name": tag, "draft": False, "assets": []},
    )
    tag_error = "Invalid release tag"
    observed = (
        tag_error in result.stderr,
        (tmp_path / "info.txt").exists(),
    )
    expected = (True, False)
    assert observed == expected, f"the tag must be refused: {result.stderr}"
