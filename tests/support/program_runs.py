# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""A fake ``subprocess.run`` that records commands and answers one exit code."""

import subprocess


class FakeProgramRun:
    """Record every command with its keyword arguments; exit with one code."""

    def __init__(self, returncode: int = 0) -> None:
        """Store the exit code and start with no recorded calls."""
        self.returncode = returncode
        self.commands: list[list[str]] = []
        self.options: list[dict[str, object]] = []

    def __call__(
        self, command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        """Record the call and return a finished process."""
        self.commands.append(command)
        self.options.append(kwargs)
        return subprocess.CompletedProcess(command, self.returncode)
