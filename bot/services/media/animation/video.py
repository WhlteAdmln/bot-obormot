# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Frame extraction from WEBM and MP4 videos through ffmpeg."""

import math
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from bot.errors import MediaError
from bot.services.media.animation.jpeg import image_to_bytes
from bot.services.media.animation.limits import (
    MAX_DIMENSION,
    MAX_DURATION,
    MAX_FRAMES,
    MAX_VIDEO_PIXELS,
    PROCESS_TIMEOUT,
)

# Minimum number of header bytes needed to see the MP4 "ftyp" marker.
_MIN_MP4_HEAD_LENGTH = 8


def _command_environment(name: str) -> dict[str, str]:
    """Return an environment that resolves the requested executable."""
    executable = shutil.which(name)
    if executable is None:
        msg = f"Required executable not found: {name}"
        raise FileNotFoundError(msg)

    executable_directory = str(Path(executable).absolute().parent)
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join((executable_directory, os.defpath))
    return environment


def _check_container(data: bytes) -> None:
    """Отклоняет данные, которые не похожи на контейнер WEBM или MP4."""
    head = data[:12]
    is_webm = head[:4] == b"\x1a\x45\xdf\xa3"
    is_mp4 = len(head) >= _MIN_MP4_HEAD_LENGTH and head[4:8] == b"ftyp"

    if not (is_webm or is_mp4):
        msg = "Неподдерживаемый формат видео."
        raise MediaError(msg)


def _probe_dimensions(working_directory: Path) -> tuple[int, int]:
    """Определяет размер первого видеопотока без разрешения сетевых протоколов."""
    result = subprocess.run(
        [
            "/usr/bin/env",
            "ffprobe",
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=s=x:p=0",
            "animation.webm",
        ],
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
        cwd=working_directory,
        env=_command_environment("ffprobe"),
    )

    if result.returncode != 0:
        msg = f"ffprobe error: {result.stderr.decode(errors='replace')}"
        raise RuntimeError(msg)

    lines = result.stdout.decode(errors="replace").strip().splitlines()

    try:
        width_text, height_text = lines[0].split("x", 1)
        width, height = int(width_text), int(height_text)
    except (IndexError, ValueError) as error:
        msg = "Cannot determine video dimensions"
        raise ValueError(msg) from error

    if width <= 0 or height <= 0:
        msg = "Invalid video dimensions"
        raise ValueError(msg)

    return width, height


def extract_video(data: bytes) -> list[bytes]:
    """Извлекает ограниченное число кадров из WEBM или MP4."""
    _check_container(data)

    with tempfile.TemporaryDirectory() as temp_dir:
        working_directory = Path(temp_dir)
        video_path = working_directory / "animation.webm"

        video_path.write_bytes(data)

        probe = subprocess.run(
            [
                "/usr/bin/env",
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                "animation.webm",
            ],
            capture_output=True,
            timeout=PROCESS_TIMEOUT,
            check=False,
            cwd=working_directory,
            env=_command_environment("ffprobe"),
        )

        if probe.returncode != 0:
            msg = f"ffprobe error: {probe.stderr.decode(errors='replace')}"
            raise RuntimeError(msg)

        duration_text = probe.stdout.decode().strip()

        if not duration_text or duration_text == "N/A":
            msg = "Cannot determine video duration"
            raise ValueError(msg)

        duration = float(duration_text)

        if not math.isfinite(duration) or duration <= 0:
            msg = "Invalid video duration"
            raise ValueError(msg)

        width, height = _probe_dimensions(working_directory)

        if width * height > MAX_VIDEO_PIXELS:
            msg = "Разрешение исходного видео слишком большое."
            raise MediaError(msg)

        duration = min(duration, MAX_DURATION)
        fps = MAX_FRAMES / duration
        filter_path = working_directory / "video_filter.txt"
        filter_path.write_text(
            f"fps={fps},"
            f"scale={MAX_DIMENSION}:{MAX_DIMENSION}:"
            "force_original_aspect_ratio=decrease,"
            f"trim=duration={MAX_DURATION},"
            f"trim=end_frame={MAX_FRAMES}",
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                "/usr/bin/env",
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-protocol_whitelist",
                "file",
                "-max_alloc",
                "1073741824",
                "-threads",
                "1",
                "-i",
                "animation.webm",
                "-filter_script:v",
                "video_filter.txt",
                "-y",
                "frame_%02d.png",
            ],
            capture_output=True,
            timeout=PROCESS_TIMEOUT,
            check=False,
            cwd=working_directory,
            env=_command_environment("ffmpeg"),
        )

        if result.returncode != 0:
            msg = f"ffmpeg error: {result.stderr.decode(errors='replace')}"
            raise RuntimeError(msg)

        files = sorted(working_directory.glob("frame_*.png"))

        if not files:
            msg = "No frames extracted from video"
            raise ValueError(msg)

        frames = []

        for file in files:
            with Image.open(file) as image:
                frames.append(image_to_bytes(image))

        return frames
