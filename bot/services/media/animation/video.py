import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from bot.services.media.animation.limits import (
    MAX_DIMENSION,
    MAX_DURATION,
    MAX_FRAMES,
    PROCESS_TIMEOUT,
)
from bot.services.media.animation.jpeg import image_to_bytes


def extract_video(data: bytes) -> list[bytes]:
    """Извлекает кадры WEBM через временный файл."""

    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / "animation.webm"
        output_pattern = str(Path(temp_dir) / "frame_%02d.png")

        video_path.write_bytes(data)

        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PROCESS_TIMEOUT,
            check=False,
        )

        if probe.returncode != 0:
            raise RuntimeError(
                f"ffprobe error: {probe.stderr.decode(errors='replace')}"
            )

        duration_text = probe.stdout.decode().strip()

        if not duration_text or duration_text == "N/A":
            raise ValueError("Cannot determine WEBM duration")

        duration = float(duration_text)

        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Invalid WEBM duration")

        duration = min(duration, MAX_DURATION)
        fps = MAX_FRAMES / duration

        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
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
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=PROCESS_TIMEOUT,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg error: {result.stderr.decode(errors='replace')}"
            )

        files = sorted(Path(temp_dir).glob("frame_*.png"))

        if not files:
            raise ValueError("No frames extracted from WEBM")

        frames = []

        for file in files:
            with Image.open(file) as image:
                frames.append(image_to_bytes(image))

        return frames
