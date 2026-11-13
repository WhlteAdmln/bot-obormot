# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Frame extraction from WEBM and MP4 videos through ffmpeg."""

import math
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


def _check_container(data: bytes) -> None:
    """Отклоняет данные, которые не похожи на контейнер WEBM или MP4."""
    head = data[:12]
    is_webm = head[:4] == b"\x1a\x45\xdf\xa3"
    is_mp4 = len(head) >= _MIN_MP4_HEAD_LENGTH and head[4:8] == b"ftyp"

    if not (is_webm or is_mp4):
        msg = "Неподдерживаемый формат видео."
        raise MediaError(msg)


def _probe_dimensions(video_path: Path) -> tuple[int, int]:
    """Определяет размер первого видеопотока без разрешения сетевых протоколов."""
    result = subprocess.run(
        [
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
            str(video_path),
        ],
        capture_output=True,
        timeout=PROCESS_TIMEOUT,
        check=False,
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
        video_path = Path(temp_dir) / "animation.webm"
        output_pattern = str(Path(temp_dir) / "frame_%02d.png")

        video_path.write_bytes(data)

        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            timeout=PROCESS_TIMEOUT,
            check=False,
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

        width, height = _probe_dimensions(video_path)

        if width * height > MAX_VIDEO_PIXELS:
            msg = "Разрешение исходного видео слишком большое."
            raise MediaError(msg)

        duration = min(duration, MAX_DURATION)
        fps = MAX_FRAMES / duration

        result = subprocess.run(
            [
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
                str(video_path),
                "-t",
                str(MAX_DURATION),
                "-vf",
                (
                    f"fps={fps},"
                    f"scale={MAX_DIMENSION}:{MAX_DIMENSION}:"
                    "force_original_aspect_ratio=decrease"
                ),
                "-frames:v",
                str(MAX_FRAMES),
                "-y",
                output_pattern,
            ],
            capture_output=True,
            timeout=PROCESS_TIMEOUT,
            check=False,
        )

        if result.returncode != 0:
            msg = f"ffmpeg error: {result.stderr.decode(errors='replace')}"
            raise RuntimeError(msg)

        files = sorted(Path(temp_dir).glob("frame_*.png"))

        if not files:
            msg = "No frames extracted from video"
            raise ValueError(msg)

        frames = []

        for file in files:
            with Image.open(file) as image:
                frames.append(image_to_bytes(image))

        return frames
