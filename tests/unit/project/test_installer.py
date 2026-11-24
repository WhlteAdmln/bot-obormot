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

import pytest

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
    assert shell_path is not None, "A POSIX shell is required"

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


def calls_of(app_home: Path) -> list[list[str]]:
    """Return the commands recorded by the fake CLI."""
    path = app_home / "calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def installed_version(app_home: Path) -> str:
    """Return the installed bot-obormot distribution version."""
    metadata_files = list(
        (app_home / ".venv").glob(
            "lib/python*/site-packages/bot_obormot-*.dist-info/METADATA"
        )
    )
    assert len(metadata_files) == 1
    for line in metadata_files[0].read_text(encoding="utf-8").splitlines():
        if line.startswith("Version: "):
            return line.removeprefix("Version: ")
    message = "Installed bot-obormot metadata has no Version field."
    raise AssertionError(message)


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
    assert result.returncode == 0, result.stdout + result.stderr
    app_home = user_home / "bot-obormot"
    expected_installed_version = "1.2.3"
    assert installed_version(app_home) == expected_installed_version
    return app_home


def publish_version_two(release_dir: Path) -> None:
    """Publish a second fake release over the first one."""
    write_checksums(release_dir, create_test_wheel(release_dir, version="2.0.0"))


def sha256_of(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_help_lists_every_option() -> None:
    result = run_installer("--help")

    assert result.returncode == 0
    for flag in ("--version", "--nightly", "--systemd", "--with-tgs", "--upgrade"):
        assert flag in result.stdout


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (("--version", "abc"), "Invalid version"),
        (("--version", "1.0.0", "--nightly"), "only one of"),
        (("--upgrade", "--systemd"), "never touches the systemd unit"),
        (("--unknown",), "Unknown argument"),
        (("--version",), "requires a value"),
    ],
)
def test_invalid_arguments_fail_before_any_installation(
    arguments: tuple[str, ...], message: str, user_home: Path
) -> None:
    result = run_installer(*arguments, home=user_home)

    assert result.returncode != 0
    assert message in result.stderr
    assert not (user_home / "bot-obormot").exists()


def test_fresh_install_runs_init_doctor_and_systemd(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release
    app_home = user_home / "custom home"

    result = run_installer(
        "--systemd", release_url=release_url, home=user_home, app_home=app_home
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (app_home / ".venv" / "bin" / "bot-obormot").is_file()
    expected_number = 0o600
    assert (app_home / ".env").stat().st_mode & 0o777 == expected_number
    assert (app_home / "service-installed").is_file()
    assert calls_of(app_home) == [
        ["init"],
        ["doctor", "--offline"],
        ["service", "install", "--user"],
    ]
    manual_start_note = "does not enable or start"
    assert manual_start_note in result.stdout


def test_fresh_install_succeeds_when_doctor_reports_template_values(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release

    result = run_installer(
        release_url=release_url,
        home=user_home,
        extra_env={"FAKE_DOCTOR_FAIL": "1"},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    doctor_warning = "doctor reported problems"
    assert doctor_warning in result.stdout
    assert (user_home / "bot-obormot" / ".env").is_file()


def test_with_tgs_installs_the_optional_extra(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release

    result = run_installer("--with-tgs", release_url=release_url, home=user_home)

    assert result.returncode == 0, result.stdout + result.stderr
    expected_installed_version = "1.2.3"
    assert installed_version(user_home / "bot-obormot") == expected_installed_version


def test_checksum_mismatch_stops_the_installation(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    wheel_path = next(release_dir.glob("bot_obormot-*.whl"))
    write_checksums(release_dir, wheel_path, corrupt=True)

    result = run_installer(release_url=release_url, home=user_home)

    assert result.returncode != 0
    checksum_error = "SHA-256 verification failed"
    assert checksum_error in result.stderr
    assert not (user_home / "bot-obormot").exists()


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

    assert result.returncode != 0
    missing_wheel_error = "v0.1.1 has no wheel asset"
    assert missing_wheel_error in result.stderr
    installer_path = "/v0.1.1/install.sh"
    assert installer_path in result.stderr
    assert not (user_home / "bot-obormot").exists()


def test_existing_home_is_refused_without_upgrade(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, _ = local_release
    app_home = user_home / "bot-obormot"
    app_home.mkdir()
    marker = app_home / "keep.txt"
    marker.write_text("existing data", encoding="utf-8")

    result = run_installer(release_url=release_url, home=user_home)

    assert result.returncode != 0
    upgrade_hint = "Use --upgrade"
    assert upgrade_hint in result.stderr
    expected_text = "existing data"
    assert marker.read_text(encoding="utf-8") == expected_text


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

    assert result.returncode == 0, result.stdout + result.stderr
    assert sha256_of(env_path) == env_hash
    assert sha256_of(database) == database_hash
    assert not old_marker.exists()
    expected_installed_version = "2.0.0"
    assert installed_version(app_home) == expected_installed_version
    assert not (app_home / ".venv.new").exists()
    assert not (app_home / ".venv.prev").exists()
    restart_command = "systemctl --user restart bot-obormot.service"
    assert restart_command in result.stdout
    assert calls_of(app_home)[-1] == ["doctor", "--offline"]
    assert ["service", "install", "--user"] not in calls_of(app_home)


def test_upgrade_leaves_no_staged_path_in_the_environment_files(
    user_home: Path, local_release: tuple[str, Path]
) -> None:
    release_url, release_dir = local_release
    app_home = install_version_one(release_url, user_home)
    publish_version_two(release_dir)

    result = run_installer("--upgrade", release_url=release_url, home=user_home)

    assert result.returncode == 0, result.stdout + result.stderr
    environment = app_home / ".venv"
    files = [
        path
        for path in (*(environment / "bin").iterdir(), environment / "pyvenv.cfg")
        if path.is_file() and not path.is_symlink()
    ]
    assert environment / "bin" / "bot-obormot" in files
    expected_bytes = b".venv.new"
    assert [path.name for path in files if expected_bytes in path.read_bytes()] == []
    interpreter = str(environment / "bin" / "python").encode()
    assert interpreter in (environment / "bin" / "bot-obormot").read_bytes()

    entry_point = subprocess.run(  # noqa: S603 - runs the CLI installed by the test.
        [str(environment / "bin" / "bot-obormot"), "doctor", "--offline"],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "BOT_OBORMOT_HOME": str(app_home)},
        timeout=60,
    )
    assert entry_point.returncode == 0, entry_point.stdout + entry_point.stderr


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

    assert result.returncode != 0
    doctor_error = "doctor --offline failed"
    assert doctor_error in result.stderr
    expected_text = "old"
    assert old_marker.read_text(encoding="utf-8") == expected_text
    expected_installed_version = "1.2.3"
    assert installed_version(app_home) == expected_installed_version
    assert not (app_home / ".venv.new").exists()
    assert not (app_home / ".venv.prev").exists()


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

    assert result.returncode != 0
    active_note = "user service is active"
    assert active_note in result.stderr
    expected_installed_version = "1.2.3"
    assert installed_version(app_home) == expected_installed_version
    assert not (app_home / ".venv.new").exists()


def test_embedded_python_snippets_are_valid(tmp_path: Path) -> None:
    text = INSTALLER.read_text(encoding="utf-8")
    snippets = re.findall(r"<<'PY'[^\n]*\n(.*?)\nPY\n", text, re.DOTALL)
    expected_count = 2
    assert len(snippets) == expected_count
    for number, snippet in enumerate(snippets):
        compile(snippet, f"<install.sh snippet {number}>", "exec")

    release = tmp_path / "release.json"
    release.write_text(
        json.dumps(
            {
                "tag_name": "v0.2.0",
                "draft": False,
                "assets": [{"name": "bot_obormot-0.2.0-py3-none-any.whl"}],
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "info.txt"
    subprocess.run(  # noqa: S603 - runs the test interpreter on a local snippet.
        [sys.executable, "-", str(release), str(destination), "latest"],
        input=snippets[0],
        text=True,
        check=True,
    )
    assert destination.read_text(encoding="utf-8").splitlines() == ["v0.2.0", "1"]
