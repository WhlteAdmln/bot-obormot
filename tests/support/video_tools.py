# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""A fake ``subprocess.run`` that plays ffprobe and ffmpeg for video tests."""

from pathlib import Path
from types import SimpleNamespace

from PIL import Image

_FFPROBE = "ffprobe"
_DURATION_PROBE = "format=duration"


class FakeVideoTools:
    """Answer ffprobe probes and produce one frame for every ffmpeg run."""

    def __init__(self, *, duration: bytes = b"1.0\n", size: bytes = b"32x24\n") -> None:
        """Store the probe answers and start with no recorded calls."""
        self.duration = duration
        self.size = size
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.filter_scripts: list[str] = []

    def __call__(self, command: list[str], **kwargs: object) -> SimpleNamespace:
        """Record the command and answer it like the real tool would."""
        self.calls.append((command, kwargs))
        if command[1] == _FFPROBE:
            answer = self.duration if _DURATION_PROBE in command else self.size
            return SimpleNamespace(returncode=0, stdout=answer, stderr=b"")
        working_directory = Path(str(kwargs["cwd"]))
        script = command[command.index("-filter_script:v") + 1]
        self.filter_scripts.append((working_directory / script).read_text("utf-8"))
        Image.new("RGB", (16, 12), (20, 40, 60)).save(
            working_directory / "frame_01.png", format="PNG"
        )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def commands(self, tool: str) -> list[list[str]]:
        """Return the recorded commands of one tool."""
        return [command for command, _kwargs in self.calls if command[1] == tool]

    def option(self, tool: str, name: str) -> str:
        """Return the value that follows an option in the first run of a tool."""
        command = self.commands(tool)[0]
        return command[command.index(name) + 1]
