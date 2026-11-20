# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""CI integration tests for upgrading a real v0.1.1 directory installation.

Run only by ``make installer`` when ``BOT_OBORMOT_LEGACY_SOURCE`` points to a
checkout of the v0.1.1 tag and ``dist/`` holds the release assets.
"""

import functools
import hashlib
import http.server
import os
import shutil
import sqlite3
import subprocess
import threading
import venv
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.unit.test_installer import (
    create_systemctl_stub,
    run_installer,
    systemctl_environment,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DIR = PROJECT_ROOT / "dist"
LEGACY_SOURCE_FILES = (
    "bot/main.py",
    "pyproject.toml",
    "requirements.txt",
    "requirements-lock.txt",
    "install.sh",
    "README.md",
    "README.ru.md",
    "LICENSE",
    ".env.example",
)
VALID_TOKEN = "123456789:CI_LEGACY_UPGRADE_TOKEN_0123456789"  # noqa: S105


def _sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes(directory: Path) -> dict[str, str]:
    """Hash the legacy source files that exist in the checkout."""
    return {
        relative: _sha256(directory / relative)
        for relative in LEGACY_SOURCE_FILES
        if (directory / relative).is_file()
    }


def _prepare_legacy_installation(
    legacy_source: Path, app_home: Path, *, supervisor_id: str = "1"
) -> dict[str, str]:
    """Create a 0.1.1-style directory with .env, data and an empty venv."""
    shutil.copytree(legacy_source, app_home, ignore=shutil.ignore_patterns(".git"))
    venv.EnvBuilder(with_pip=True).create(str(app_home / ".venv"))

    (app_home / "data").mkdir(exist_ok=True)
    with sqlite3.connect(app_home / "data" / "bot.db") as connection:
        connection.execute("CREATE TABLE marker (value TEXT)")
        connection.execute("INSERT INTO marker VALUES ('legacy-data')")

    env_path = app_home / ".env"
    env_path.write_text(
        f"BOT_TOKEN={VALID_TOKEN}\n"
        f"SUPERVISOR_ID={supervisor_id}\n"
        "LEGACY_UPGRADE_MARKER=preserve-me\n",
        encoding="utf-8",
    )
    env_path.chmod(0o600)
    return _source_hashes(app_home)


def _create_legacy_user_unit(user_home: Path, app_home: Path) -> tuple[Path, str]:
    """Write the user unit that 0.1.x documentation recommended."""
    unit_directory = user_home / ".config" / "systemd" / "user"
    unit_directory.mkdir(parents=True)
    unit_path = unit_directory / "bot-obormot.service"
    old_unit = (
        "[Unit]\n"
        "Description=Legacy bot-obormot service\n\n"
        "[Service]\n"
        f"WorkingDirectory={app_home}\n"
        f"ExecStart={app_home}/.venv/bin/python -m bot.main\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    unit_path.write_text(old_unit, encoding="utf-8")
    return unit_path, old_unit


@pytest.fixture
def release_server() -> Iterator[str]:
    """Serve ``dist/`` as a local release."""
    assert len(list(RELEASE_DIR.glob("bot_obormot-*.whl"))) == 1
    assert (RELEASE_DIR / "constraints.txt").is_file()
    assert (RELEASE_DIR / "SHA256SUMS").is_file()

    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(RELEASE_DIR)
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def legacy_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, dict[str, str], Path]:
    """Isolate the environment; return source, extra env and the systemctl log."""
    legacy_source = Path(os.environ["BOT_OBORMOT_LEGACY_SOURCE"]).resolve()
    assert (legacy_source / "bot" / "main.py").is_file()
    wheelhouse = Path(os.environ["PIP_FIND_LINKS"]).resolve()
    assert wheelhouse.is_dir()

    monkeypatch.setenv("PIP_NO_INDEX", "1")
    for name in ("BOT_TOKEN", "SUPERVISOR_ID", "PYTHONPATH", "FAKE_DOCTOR_FAIL"):
        monkeypatch.delenv(name, raising=False)

    fake_bin, log_path = create_systemctl_stub(tmp_path, active=False)
    return legacy_source, systemctl_environment(fake_bin, log_path), log_path


def test_real_legacy_upgrade_moves_source_and_keeps_user_data(
    tmp_path: Path,
    release_server: str,
    legacy_context: tuple[Path, dict[str, str], Path],
) -> None:
    """A real 0.1.1 tree is upgraded; doctor, the unit and the shim all work."""
    legacy_source, extra_env, systemctl_log = legacy_context
    user_home = tmp_path / "user"
    user_home.mkdir()
    app_home = user_home / "bot-obormot"
    source_hashes = _prepare_legacy_installation(legacy_source, app_home)
    env_hash = _sha256(app_home / ".env")
    database_hash = _sha256(app_home / "data" / "bot.db")
    unit_path, old_unit = _create_legacy_user_unit(user_home, app_home)

    result = run_installer(
        "--upgrade",
        release_url=release_server,
        home=user_home,
        app_home=app_home,
        extra_env=extra_env,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    legacy_dirs = list(app_home.glob(".legacy-*"))
    assert len(legacy_dirs) == 1
    assert _source_hashes(legacy_dirs[0]) == source_hashes
    assert not (app_home / "bot").exists()
    assert _sha256(app_home / ".env") == env_hash
    assert _sha256(app_home / "data" / "bot.db") == database_hash
    assert (app_home / ".venv" / "bin" / "bot-obormot").is_file()
    assert (
        unit_path.with_name("bot-obormot.service.bak").read_text(encoding="utf-8")
        == old_unit
    )
    new_unit = unit_path.read_text(encoding="utf-8")
    assert f'ExecStart="{app_home}/.venv/bin/bot-obormot" run' in new_unit
    assert "python -m bot.main" not in new_unit
    assert systemctl_log.read_text(encoding="utf-8").splitlines() == [
        "--user is-active --quiet bot-obormot.service",
        "--user daemon-reload",
    ]
    assert "FAIL" not in output
    assert "Settings: All settings are valid." in output

    # The compatibility shim must come from the wheel, not from the old tree.
    probe = subprocess.run(  # noqa: S603 - runs the venv interpreter under test.
        [
            str(app_home / ".venv" / "bin" / "python"),
            "-c",
            (
                "import bot.main, pathlib; "
                "print(pathlib.Path(bot.main.__file__).resolve())"
            ),
        ],
        cwd=app_home,
        check=False,
        capture_output=True,
        text=True,
        env={k: v for k, v in os.environ.items() if k != "PYTHONPATH"},
        timeout=60,
    )
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "site-packages" in probe.stdout


def test_real_legacy_upgrade_rolls_back_after_a_doctor_failure(
    tmp_path: Path,
    release_server: str,
    legacy_context: tuple[Path, dict[str, str], Path],
) -> None:
    """An invalid configuration restores the old source tree and the old unit."""
    legacy_source, extra_env, _systemctl_log = legacy_context
    user_home = tmp_path / "user"
    user_home.mkdir()
    app_home = user_home / "bot-obormot"
    source_hashes = _prepare_legacy_installation(
        legacy_source, app_home, supervisor_id="not-a-number"
    )
    unit_path, old_unit = _create_legacy_user_unit(user_home, app_home)

    result = run_installer(
        "--upgrade",
        release_url=release_server,
        home=user_home,
        app_home=app_home,
        extra_env=extra_env,
    )

    assert result.returncode != 0
    assert "will be restored" in result.stderr
    assert _source_hashes(app_home) == source_hashes
    assert not list(app_home.glob(".legacy-*"))
    assert unit_path.read_text(encoding="utf-8") == old_unit
