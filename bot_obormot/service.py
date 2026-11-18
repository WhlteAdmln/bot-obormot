# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Systemd service unit rendering, installation and removal."""

import os
import shutil
import tempfile
from pathlib import Path
from typing import Literal

ServiceMode = Literal["user", "system"]
UNIT_NAME = "bot-obormot.service"
SYSTEM_UNIT_DIRECTORY = Path("/etc/systemd/system")

_UNIT_TEMPLATE = """[Unit]
Description={description}
After=network-online.target
Wants=network-online.target

[Service]
{directives}

[Install]
WantedBy={wanted_by}
"""


def _escape_systemd_path(value: str) -> str:
    """Escape a path for a systemd path directive."""
    if any(character in value for character in "\x00\r\n"):
        message = "Systemd paths must not contain null bytes or line breaks."
        raise ValueError(message)
    escapes = {"\\": "\\\\", " ": r"\x20", "\t": r"\t", '"': r"\x22", "%": "%%"}
    return "".join(escapes.get(character, character) for character in value)


def _quote_systemd_value(value: str) -> str:
    """Quote a systemd value and escape specifier characters."""
    if any(character in value for character in "\x00\r\n"):
        message = "Systemd values must not contain null bytes or line breaks."
        raise ValueError(message)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    return f'"{escaped}"'


def default_unit_directory(mode: ServiceMode) -> Path:
    """Return the directory that holds units for the selected mode."""
    if mode == "system":
        return SYSTEM_UNIT_DIRECTORY
    return Path.home() / ".config" / "systemd" / "user"


def render_service_unit(home: Path, *, mode: ServiceMode) -> str:
    """Render a systemd unit without filesystem or system side effects."""
    if not home.is_absolute():
        message = "The bot-obormot home directory must be an absolute path."
        raise ValueError(message)
    if mode not in {"user", "system"}:
        message = f"Unsupported systemd service mode: {mode}"
        raise ValueError(message)

    directives = ["Type=simple"]
    if mode == "system":
        directives.extend(("User=bot-obormot", "Group=bot-obormot"))

    executable = _quote_systemd_value(str(home / ".venv" / "bin" / "bot-obormot"))
    directives.extend(
        (
            f"WorkingDirectory={_escape_systemd_path(str(home))}",
            f"Environment={_quote_systemd_value(f'BOT_OBORMOT_HOME={home}')}",
            "Environment=PYTHONUNBUFFERED=1",
            f"ExecStart={executable} run",
            "Restart=on-failure",
            "RestartSec=5",
            "UMask=0077",
        )
    )
    if mode == "system":
        directives.extend(
            (
                "",
                "# Process and filesystem sandbox.",
                "NoNewPrivileges=true",
                "PrivateTmp=true",
                "ProtectSystem=strict",
                f"ReadWritePaths={_escape_systemd_path(str(home))}",
                "ProtectKernelTunables=true",
                "ProtectKernelModules=true",
                "ProtectControlGroups=true",
                "RestrictNamespaces=true",
                "LockPersonality=true",
            )
        )

    return _UNIT_TEMPLATE.format(
        description="bot-obormot Telegram bot",
        directives="\n".join(directives),
        wanted_by="multi-user.target" if mode == "system" else "default.target",
    )


def install_service_unit(
    home: Path,
    *,
    mode: ServiceMode,
    force: bool = False,
    unit_directory: Path | None = None,
) -> Path:
    """Install a unit without enabling or starting the service.

    An existing unit is never replaced without ``force``; with ``force`` the old
    file is saved as ``<unit>.bak``.
    """
    directory = unit_directory or default_unit_directory(mode)
    unit_path = directory / UNIT_NAME
    backup_path = unit_path.with_name(f"{UNIT_NAME}.bak")
    exists = unit_path.exists() or unit_path.is_symlink()
    if exists and not force:
        message = f"Systemd unit exists: {unit_path}; pass --force to replace it."
        raise FileExistsError(message)

    content = render_service_unit(home, mode=mode)
    directory.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{UNIT_NAME}.", dir=directory
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.chmod(0o644)
        if exists:
            shutil.copy2(unit_path, backup_path)
            temporary_path.replace(unit_path)
        else:
            os.link(temporary_path, unit_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return unit_path


def uninstall_service_unit(
    *,
    mode: ServiceMode,
    unit_directory: Path | None = None,
) -> Path | None:
    """Remove the unit file without stopping or disabling the service.

    Returns the removed path, or ``None`` when no unit was installed.
    """
    unit_path = (unit_directory or default_unit_directory(mode)) / UNIT_NAME
    if not (unit_path.exists() or unit_path.is_symlink()):
        return None
    unit_path.unlink()
    return unit_path
