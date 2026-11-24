# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for animation video."""

import os

import pytest

from bot_obormot.common import process
from bot_obormot.errors import MediaError
from bot_obormot.services.media.animation import video
from tests.support.video_tools import FakeVideoTools


def _install(
    monkeypatch: pytest.MonkeyPatch,
    tools: FakeVideoTools,
) -> FakeVideoTools:
    monkeypatch.setattr(process.shutil, "which", lambda name: f"/opt/media/{name}")
    monkeypatch.setattr(process.subprocess, "run", tools)
    return tools


def _extract(monkeypatch: pytest.MonkeyPatch) -> FakeVideoTools:
    tools = _install(monkeypatch, FakeVideoTools())
    video.extract_video(b"\x1a\x45\xdf\xa3" + b"fake-webm")
    return tools


@pytest.mark.parametrize(
    "data",
    [b"\x1a\x45\xdf\xa3" + b"webm-data", b"\x00\x00\x00\x18ftypmp42" + b"mp4-data"],
    ids=["webm", "mp4"],
)
def test_extract_video_accepts_webm_and_mp4_containers(
    monkeypatch: pytest.MonkeyPatch,
    data: bytes,
) -> None:
    _install(monkeypatch, FakeVideoTools())
    frames = video.extract_video(data)
    assert len(frames) == 1, "a supported container must yield the frame"


@pytest.mark.parametrize(
    "data",
    [b"#EXTM3U\nhttps://example.invalid/video", b"", b"not-a-video"],
    ids=["playlist", "empty", "unknown"],
)
def test_extract_video_rejects_playlists_and_unknown_data(data: bytes) -> None:
    with pytest.raises(MediaError, match="формат видео"):
        video.extract_video(data)


def test_extract_video_runs_probes_by_the_resolved_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = _extract(monkeypatch)
    programs = {command[0] for command in tools.commands("ffprobe")}
    expected = {"/opt/media/ffprobe"}
    assert programs == expected, "ffprobe must start by its resolved path"


def test_extract_video_limits_both_probes_to_local_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = _extract(monkeypatch)
    protocols = [
        command[command.index("-protocol_whitelist") + 1]
        for command in tools.commands("ffprobe")
    ]
    expected = ["file", "file"]
    assert protocols == expected, "every probe must allow only local files"


def test_extract_video_probes_the_first_video_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = _extract(monkeypatch)
    option = "-select_streams"
    streams = [
        command[command.index(option) + 1]
        for command in tools.commands("ffprobe")
        if option in command
    ]
    expected = ["v:0"]
    assert streams == expected, "the size probe must read the first video stream"


def test_extract_video_runs_ffmpeg_by_the_resolved_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = _extract(monkeypatch)
    program = tools.commands("ffmpeg")[0][0]
    expected = "/opt/media/ffmpeg"
    assert program == expected, "ffmpeg must start by its resolved path"


def test_extract_video_narrows_path_of_every_tool_to_its_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = _extract(monkeypatch)
    paths = {str(kwargs["env"]["PATH"]) for _command, kwargs in tools.calls}
    expected = {os.pathsep.join(("/opt/media", os.defpath))}
    assert paths == expected, "PATH must hold the tool directory and defpath only"


def test_extract_video_rejects_a_missing_ffprobe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(process.shutil, "which", lambda _name: None)
    with pytest.raises(FileNotFoundError, match="ffprobe"):
        video.extract_video(b"\x1a\x45\xdf\xa3" + b"fake-webm")


def test_extract_video_rejects_resolution_before_running_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = _install(monkeypatch, FakeVideoTools(size=b"3840x2161\n"))
    with pytest.raises(MediaError, match="Разрешение исходного видео"):
        video.extract_video(b"\x1a\x45\xdf\xa3" + b"fake-webm")
    expected_empty = []
    assert tools.commands("ffmpeg") == expected_empty, (
        "ffmpeg must not run for oversized input"
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("-protocol_whitelist", "file"),
        ("-max_alloc", "1073741824"),
        ("-threads", "1"),
        ("-filter_script:v", "video_filter.txt"),
    ],
)
def test_extract_video_passes_resource_and_protocol_limits_to_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    expected: str,
) -> None:
    tools = _extract(monkeypatch)
    assert tools.option("ffmpeg", name) == expected, f"ffmpeg {name} is wrong"


def test_extract_video_never_lets_ffmpeg_read_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools = _extract(monkeypatch)
    flag = "-nostdin"
    assert flag in tools.commands("ffmpeg")[0], "ffmpeg must not read stdin"


@pytest.mark.parametrize(
    "fragment",
    [
        "fps=",
        f"scale={video.MAX_DIMENSION}:{video.MAX_DIMENSION}:",
        "force_original_aspect_ratio=decrease",
        f"trim=duration={video.MAX_DURATION}",
        f"trim=end_frame={video.MAX_FRAMES}",
    ],
)
def test_extract_video_bounds_the_frames_in_the_filter_script(
    monkeypatch: pytest.MonkeyPatch,
    fragment: str,
) -> None:
    tools = _extract(monkeypatch)
    assert fragment in tools.filter_scripts[0], f"the filter must contain {fragment}"
