# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation video."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import video


def test_video_container_sniffer_accepts_webm_and_mp4() -> None:
    """Video container sniffer accepts webm and mp4."""
    video._check_container(b"\x1a\x45\xdf\xa3" + b"webm-data")
    video._check_container(b"\x00\x00\x00\x18ftypmp42" + b"mp4-data")


def test_video_container_sniffer_rejects_playlist_and_unknown_data() -> None:
    """Video container sniffer rejects playlist and unknown data."""
    for data in (b"#EXTM3U\nhttps://example.invalid/video", b"", b"not-a-video"):
        with pytest.raises(MediaError, match="формат видео"):
            video._check_container(data)


def test_probe_dimensions_uses_local_file_protocol_and_parses_dimensions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Probe dimensions uses local file protocol and parses dimensions."""
    calls = []

    def fake_run(command: object, **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"1920x1080\n", stderr=b"")

    monkeypatch.setattr(video.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(video.subprocess, "run", fake_run)

    assert video._probe_dimensions(tmp_path) == (1920, 1080)
    command, kwargs = calls[0]
    assert command[0] == "/usr/bin/env"
    assert command[1] == "ffprobe"
    assert command[command.index("-protocol_whitelist") + 1] == "file"
    assert command[command.index("-select_streams") + 1] == "v:0"
    assert kwargs["cwd"] == tmp_path
    assert kwargs["env"]["PATH"].split(os.pathsep)[0] == "/usr/bin"


def test_command_environment_rejects_missing_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Command environment rejects missing executable."""
    monkeypatch.setattr(video.shutil, "which", lambda _name: None)

    with pytest.raises(FileNotFoundError, match="ffprobe"):
        video._command_environment("ffprobe")


def test_extract_video_rejects_resolution_before_running_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extract video rejects resolution before running ffmpeg."""
    calls = []

    def fake_run(command: object, **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if command[1] == "ffprobe" and "format=duration" in command:
            return SimpleNamespace(returncode=0, stdout=b"1.0\n", stderr=b"")
        if command[1] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout=b"3840x2161\n", stderr=b"")
        msg = "ffmpeg must not run for oversized input"
        raise AssertionError(msg)

    monkeypatch.setattr(video.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(video.subprocess, "run", fake_run)

    with pytest.raises(MediaError, match="Разрешение исходного видео"):
        video.extract_video(b"\x1a\x45\xdf\xa3" + b"fake-webm")

    assert len(calls) == 2
    assert all(call[0] == "/usr/bin/env" and call[1] == "ffprobe" for call in calls)


def test_extract_video_passes_resource_and_protocol_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extract video passes resource and protocol limits."""
    calls = []
    filter_scripts = []

    def fake_run(command: object, **kwargs: object) -> SimpleNamespace:
        calls.append((command, kwargs))
        if command[1] == "ffprobe" and "format=duration" in command:
            return SimpleNamespace(returncode=0, stdout=b"1.0\n", stderr=b"")
        if command[1] == "ffprobe":
            return SimpleNamespace(returncode=0, stdout=b"32x24\n", stderr=b"")

        assert command[0] == "/usr/bin/env"
        assert command[1] == "ffmpeg"
        working_directory = Path(kwargs["cwd"])
        filter_path = working_directory / command[command.index("-filter_script:v") + 1]
        filter_scripts.append(filter_path.read_text(encoding="utf-8"))
        Image.new("RGB", (16, 12), (20, 40, 60)).save(
            working_directory / "frame_01.png", format="PNG"
        )
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(video.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(video.subprocess, "run", fake_run)

    frames = video.extract_video(b"\x1a\x45\xdf\xa3" + b"fake-webm")

    assert len(frames) == 1
    ffprobes = [call for call, _kwargs in calls if call[1] == "ffprobe"]
    ffmpeg = next(call for call, _kwargs in calls if call[1] == "ffmpeg")
    assert len(ffprobes) == 2
    for command in ffprobes:
        assert command[command.index("-protocol_whitelist") + 1] == "file"
    assert "-nostdin" in ffmpeg
    assert ffmpeg[ffmpeg.index("-protocol_whitelist") + 1] == "file"
    assert ffmpeg[ffmpeg.index("-max_alloc") + 1] == "1073741824"
    assert ffmpeg[ffmpeg.index("-threads") + 1] == "1"
    assert ffmpeg[ffmpeg.index("-filter_script:v") + 1] == "video_filter.txt"
    filter_script = filter_scripts[0]
    assert "fps=" in filter_script
    assert f"scale={video.MAX_DIMENSION}:{video.MAX_DIMENSION}:" in filter_script
    assert "force_original_aspect_ratio=decrease" in filter_script
    assert f"trim=duration={video.MAX_DURATION}" in filter_script
    assert f"trim=end_frame={video.MAX_FRAMES}" in filter_script
