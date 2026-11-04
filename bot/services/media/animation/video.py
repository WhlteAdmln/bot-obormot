import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from bot.errors import MediaError
from bot.services.media.animation.limits import (
    MAX_DIMENSION,
    MAX_DURATION,
    MAX_FRAMES,
    MAX_VIDEO_PIXELS,
    PROCESS_TIMEOUT,
)
from bot.services.media.animation.jpeg import image_to_bytes


def _check_container(data: bytes) -> None:
    """Отклоняет данные, которые не похожи на контейнер WEBM или MP4."""
    head = data[:12]
    is_webm = head[:4] == b"\x1a\x45\xdf\xa3"
    is_mp4 = len(head) >= 8 and head[4:8] == b"ftyp"

    if not (is_webm or is_mp4):
        raise MediaError("Неподдерживаемый формат видео.")


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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=PROCESS_TIMEOUT,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr.decode(errors='replace')}")

    lines = result.stdout.decode(errors="replace").strip().splitlines()

    try:
        width_text, height_text = lines[0].split("x", 1)
        width, height = int(width_text), int(height_text)
    except (IndexError, ValueError) as error:
        raise ValueError("Cannot determine video dimensions") from error

    if width <= 0 or height <= 0:
        raise ValueError("Invalid video dimensions")

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
            raise ValueError("Cannot determine video duration")

        duration = float(duration_text)

        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Invalid video duration")

        width, height = _probe_dimensions(video_path)

        if width * height > MAX_VIDEO_PIXELS:
            raise MediaError("Разрешение исходного видео слишком большое.")

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
            raise ValueError("No frames extracted from video")

        frames = []

        for file in files:
            with Image.open(file) as image:
                frames.append(image_to_bytes(image))

        return frames
