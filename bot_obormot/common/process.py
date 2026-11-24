# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""The one place that starts external programs."""

import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

_NUL = "\0"


def _validate_argv(name: str, arguments: Sequence[str]) -> None:
    """Reject a program name that is a path or an option, and NUL bytes."""
    separators = [separator for separator in (os.sep, os.altsep) if separator]
    if (
        not name
        or name.startswith("-")
        or _NUL in name
        or any(separator in name for separator in separators)
    ):
        msg = f"Invalid program name: {name!r}"
        raise ValueError(msg)
    if any(_NUL in argument for argument in arguments):
        msg = f"Argument of {name} contains a NUL byte"
        raise ValueError(msg)


def resolve_program(name: str) -> str:
    """Return the absolute path of a program found on PATH."""
    executable = shutil.which(name)
    if executable is None:
        msg = f"{name} was not found on this system."
        raise FileNotFoundError(msg)
    return str(Path(executable).absolute())


def _narrowed_environment(executable: str) -> dict[str, str]:
    """Return the environment with PATH cut to the program directory and defpath."""
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((str(Path(executable).parent), os.defpath))
    return environment


def run_program(
    name: str,
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: float | None = None,
    capture_output: bool = False,
    narrow_path: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    """Run a program from PATH with a validated argv, no shell and no exit check.

    With ``narrow_path``, the program sees a ``PATH`` of its own directory
    followed by the system default search path; otherwise it inherits the
    environment.
    """
    _validate_argv(name, arguments)
    executable = resolve_program(name)
    environment = _narrowed_environment(executable) if narrow_path else None
    return subprocess.run(  # noqa: S603 - validated argv, resolved program, no shell.
        [executable, *arguments],
        capture_output=capture_output,
        timeout=timeout,
        check=False,
        cwd=cwd,
        env=environment,
    )
