# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

import asyncio
import base64
import gzip
import io
import json
import os
import struct
import threading
import time
import warnings
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from bot.errors import MediaError
from bot.services import media
from bot.services.media import animation
from bot.services.media import pipeline as media_pipeline
from bot.services.media.animation import tgs, video
from bot.services.media.animation.gif import extract_gif
from bot.services.media.animation.limits import MAX_FRAMES
from bot.services.media.animation.sampling import sample_frame_indices
from bot.services.media.contact_sheet import build_contact_sheet
from bot.services.media.limits import MAX_IMAGE_PIXELS
from bot.services.media.safety import check_image_size, configure_pillow_limits
from bot.services.media.sniff import sniff_media_type, verify_declared_type


def make_message(**values):
    defaults = {
        "photo": None,
        "animation": None,
        "video": None,
        "sticker": None,
        "document": None,
        "caption": None,
        "text": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_get_media_info_prefers_photo_and_uses_largest_photo():
    message = make_message(
        photo=[SimpleNamespace(file_id="small"), SimpleNamespace(file_id="large")],
    )

    assert media.get_media_info(message) == ("large", "image")


def test_get_media_info_classifies_stickers_and_documents():
    animated_sticker = make_message(
        sticker=SimpleNamespace(
            file_id="tgs-id",
            is_animated=True,
            is_video=False,
        ),
    )
    video_sticker = make_message(
        sticker=SimpleNamespace(
            file_id="webm-id",
            is_animated=False,
            is_video=True,
        ),
    )
    gif_document = make_message(
        document=SimpleNamespace(
            file_id="gif-id",
            file_name="IMAGE.GIF",
            mime_type="application/octet-stream",
        ),
    )

    assert media.get_media_info(animated_sticker) == ("tgs-id", "tgs")
    assert media.get_media_info(video_sticker) == ("webm-id", "webm")
    assert media.get_media_info(gif_document) == ("gif-id", "gif")


def test_get_media_info_classifies_video_documents_by_mime_type():
    message = make_message(
        document=SimpleNamespace(
            file_id="video-id",
            file_name="clip.bin",
            mime_type="video/mp4",
        ),
    )

    assert media.get_media_info(message) == ("video-id", "mp4")


def test_build_contact_sheet_combines_frames_into_one_jpeg():
    frames = []
    for color in ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)):
        output = io.BytesIO()
        Image.new("RGB", (40, 30), color).save(output, format="JPEG")
        frames.append(output.getvalue())

    result = build_contact_sheet(frames)

    with Image.open(io.BytesIO(result)) as sheet:
        assert sheet.format == "JPEG"
        assert sheet.size == (3 * 512, 2 * 384)


def test_build_contact_sheet_returns_single_frame_unchanged():
    frame = b"one-frame"
    assert build_contact_sheet([frame]) == frame


def test_build_contact_sheet_rejects_empty_or_excessive_frames():
    with pytest.raises(ValueError, match="without frames"):
        build_contact_sheet([])
    with pytest.raises(ValueError, match="at most"):
        build_contact_sheet([b"x"] * (MAX_FRAMES + 1))


def test_get_user_content_describes_animation_contact_sheet():
    message = make_message(caption=None, sticker=None, text="ignored")
    content = media.get_user_content(
        message,
        ["data:image/jpeg;base64,combined"],
        "tgs",
    )

    assert len(content) == 2
    assert content[1]["image_url"]["url"] == "data:image/jpeg;base64,combined"
    assert "одно нумерованное изображение-монтаж" in content[0]["text"]
    assert "сверху вниз" in content[0]["text"]


def test_prepare_image_returns_jpeg_data_url_and_composites_transparency():
    source = Image.new("RGBA", (12, 8), (255, 0, 0, 0))
    output = io.BytesIO()
    source.save(output, format="PNG")

    result = media.prepare_image(output.getvalue())

    assert result.startswith("data:image/jpeg;base64,")
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (12, 8)


def test_sample_frame_indices_matches_even_sampling_and_limits_count():
    assert sample_frame_indices(1) == [0]
    assert sample_frame_indices(4) == [0, 1, 2, 3]
    assert sample_frame_indices(20) == [0, 4, 8, 11, 15, 19]


def test_sample_frame_indices_rejects_empty_animation():
    with pytest.raises(ValueError, match="does not contain frames"):
        sample_frame_indices(0)


def test_animation_dispatcher_routes_formats_and_preserves_patch_points(monkeypatch):
    calls = []
    monkeypatch.setattr(
        animation, "_extract_gif", lambda data: calls.append(("gif", data)) or [b"g"]
    )
    monkeypatch.setattr(
        animation, "_extract_tgs", lambda data: calls.append(("tgs", data)) or [b"t"]
    )
    monkeypatch.setattr(
        animation,
        "_extract_webm",
        lambda data: calls.append(("video", data)) or [b"v"],
    )

    assert animation._extract_frames(b"1", "gif") == [b"g"]
    assert animation._extract_frames(b"2", "tgs") == [b"t"]
    assert animation._extract_frames(b"3", "mp4") == [b"v"]
    assert calls == [("gif", b"1"), ("tgs", b"2"), ("video", b"3")]


def test_image_to_bytes_encodes_bounded_jpeg_frame():
    source = Image.new("RGBA", (1400, 900), (30, 60, 90, 128))

    encoded = animation._image_to_bytes(source)

    with Image.open(io.BytesIO(encoded)) as image:
        assert image.format == "JPEG"
        assert max(image.size) <= 768
        assert image.mode == "RGB"


@pytest.mark.asyncio
async def test_process_media_uses_canonical_media_dependencies(monkeypatch):
    message = make_message()
    calls = []

    async def fake_download(received_message, file_id):
        calls.append(("download", received_message, file_id))
        return b"GIF89a" + b"animation-data"

    async def fake_extract(data, media_type):
        calls.append(("extract", data, media_type))
        return [b"frame-1", b"frame-2"]

    def fake_contact_sheet(frames):
        calls.append(("contact_sheet", frames))
        return b"combined-frames"

    def fake_prepare(image_data):
        calls.append(("prepare", image_data))
        return f"encoded:{image_data.decode()}"

    monkeypatch.setattr(media, "download_telegram_file", fake_download)
    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)
    monkeypatch.setattr(media, "prepare_image", fake_prepare)

    result = await media_pipeline.process_media(
        message,
        "gif",
        "file-id",
        downloader=media.download_telegram_file,
        animation_extractor=media.extract_animation_frames,
        image_preparer=media.prepare_image,
        contact_sheet_builder=fake_contact_sheet,
    )

    assert result == ["encoded:combined-frames"]
    assert calls[:3] == [
        ("download", message, "file-id"),
        ("extract", b"GIF89a" + b"animation-data", "gif"),
        ("contact_sheet", [b"frame-1", b"frame-2"]),
    ]
    assert calls[3] == ("prepare", b"combined-frames")


@pytest.mark.asyncio
async def test_animation_dispatch_errors_are_wrapped_as_media_error():
    with pytest.raises(MediaError, match="Failed to process unknown animation"):
        await animation.extract_animation_frames(b"data", "unknown")


def test_extract_gif_returns_at_most_six_jpeg_frames():
    frames = [Image.new("RGB", (16, 12), (index * 20, 80, 160)) for index in range(9)]
    source = io.BytesIO()
    frames[0].save(
        source,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
    )

    extracted = extract_gif(source.getvalue())

    assert len(extracted) == 6
    for frame in extracted:
        with Image.open(io.BytesIO(frame)) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"


@pytest.mark.asyncio
async def test_process_media_wraps_unexpected_pipeline_errors(monkeypatch):
    async def fake_download(message, file_id):
        return b"GIF89a" + b"broken-animation"

    async def fake_extract(data, media_type):
        msg = "decoder failed"
        raise ValueError(msg)

    monkeypatch.setattr(media, "download_telegram_file", fake_download)
    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)

    with pytest.raises(MediaError, match="Failed to prepare gif media"):
        await media.process_media(make_message(), "gif", "file-id")


def tiny_gif(width: int, height: int) -> bytes:
    """Минимальный GIF с указанным логическим размером холста."""
    header = b"GIF89a" + struct.pack("<HHBBB", width, height, 0x80, 0, 0)
    header += bytes([0, 0, 0, 255, 255, 255])
    frame = b"," + struct.pack("<HHHHB", 0, 0, 1, 1, 0) + bytes([2, 2, 0x44, 0x01, 0])
    return header + frame + b";"


def test_huge_gif_canvas_is_rejected_before_frame_decode():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", Image.DecompressionBombWarning)
        with pytest.raises(MediaError, match="слишком большое"):
            extract_gif(tiny_gif(13000, 13000))


def test_gif_frame_count_limit_is_enforced(monkeypatch):
    frames = [Image.new("RGB", (2, 2), (index, 20, 30)) for index in range(3)]
    source = io.BytesIO()
    frames[0].save(
        source,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=50,
        loop=0,
    )
    monkeypatch.setattr("bot.services.media.animation.gif.MAX_GIF_FRAMES", 2)

    with pytest.raises(MediaError, match="слишком много кадров"):
        extract_gif(source.getvalue())


def test_check_image_size_rejects_invalid_and_oversized_dimensions():
    with pytest.raises(MediaError):
        check_image_size(SimpleNamespace(size=(0, 10)), 100)
    with pytest.raises(MediaError):
        check_image_size(SimpleNamespace(size=(11, 10)), 100)
    check_image_size(SimpleNamespace(size=(10, 10)), 100)


def test_configure_pillow_limits_sets_global_decompression_limit(monkeypatch):
    # Не оставляем глобальный warning filter изменённым для других тестов.
    monkeypatch.setattr(warnings, "filters", warnings.filters.copy())
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", None)
    configure_pillow_limits()
    assert Image.MAX_IMAGE_PIXELS == MAX_IMAGE_PIXELS
    assert any(
        action == "error" and category is Image.DecompressionBombWarning
        for action, _message, category, _module, _lineno in warnings.filters
    )


@pytest.mark.asyncio
async def test_run_limited_caps_concurrent_image_jobs(monkeypatch):
    monkeypatch.setattr(media_pipeline, "_image_jobs", asyncio.Semaphore(2))
    guard = threading.Lock()
    active = 0
    maximum = 0

    def work(value):
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
        try:
            time.sleep(0.03)
            return value
        finally:
            with guard:
                active -= 1

    results = await asyncio.gather(
        *(media_pipeline._run_limited(work, value) for value in range(7))
    )

    assert results == list(range(7))
    assert maximum == 2


# TGS security checks: validate compressed data before it reaches rlottie.
def test_validate_tgs_accepts_bounded_gzip_json():
    data = gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))

    tgs.validate_tgs(data)


def test_validate_tgs_rejects_gzip_decompression_bomb():
    data = gzip.compress(b"0" * (tgs.MAX_TGS_JSON + 1))

    with pytest.raises(MediaError, match="после распаковки"):
        tgs.validate_tgs(data)


def test_validate_tgs_rejects_compressed_data_over_limit():
    data = os.urandom(tgs.MAX_TGS_COMPRESSED + 1)

    with pytest.raises(MediaError, match="Стикер слишком большой"):
        tgs.validate_tgs(data)


def test_validate_tgs_rejects_invalid_gzip_and_trailing_data():
    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.validate_tgs(b"not-a-gzip-file")

    valid = gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))
    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.validate_tgs(valid + b"trailing-data")
    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.validate_tgs(valid[:-3])


@pytest.mark.parametrize(
    "document",
    [
        {"w": 0, "h": 512},
        {"w": 1025, "h": 512},
        {"w": 512, "h": -1},
        {"w": True, "h": 512},
        {"w": 512.0, "h": 512},
        [512, 512],
    ],
)
def test_validate_tgs_rejects_invalid_canvas(document):
    data = gzip.compress(json.dumps(document).encode("utf-8"))

    with pytest.raises(MediaError, match="размер анимации"):
        tgs.validate_tgs(data)


def test_extract_tgs_validates_before_importing_rlottie(monkeypatch):
    imported_modules: list[str] = []
    monkeypatch.setattr(tgs.importlib, "import_module", imported_modules.append)

    with pytest.raises(MediaError, match="Некорректный файл"):
        tgs.extract_tgs(b"not-a-gzip-file")

    assert imported_modules == []


def test_extract_tgs_imports_rlottie_for_valid_animation(monkeypatch):
    def get_total_frames() -> int:
        return 1

    def render_frame(frame_num: int) -> Image.Image:
        return Image.new("RGB", (1, 1))

    fake_animation = SimpleNamespace(
        lottie_animation_get_totalframe=get_total_frames,
        render_pillow_frame=render_frame,
    )

    def fake_from_tgs(_path: str) -> AbstractContextManager[SimpleNamespace]:
        return nullcontext(fake_animation)

    imports: list[str] = []

    def fake_import_module(name: str) -> SimpleNamespace:
        imports.append(name)
        return SimpleNamespace(
            LottieAnimation=SimpleNamespace(from_tgs=fake_from_tgs),
        )

    monkeypatch.setattr(tgs.importlib, "import_module", fake_import_module)
    data = gzip.compress(json.dumps({"w": 512, "h": 512}).encode("utf-8"))

    frames = tgs.extract_tgs(data)

    assert imports == ["rlottie_python"]
    assert len(frames) == 1
    with Image.open(io.BytesIO(frames[0])) as image:
        assert image.format == "JPEG"


def test_video_container_sniffer_accepts_webm_and_mp4():
    video._check_container(b"\x1a\x45\xdf\xa3" + b"webm-data")
    video._check_container(b"\x00\x00\x00\x18ftypmp42" + b"mp4-data")


def test_video_container_sniffer_rejects_playlist_and_unknown_data():
    for data in (b"#EXTM3U\nhttps://example.invalid/video", b"", b"not-a-video"):
        with pytest.raises(MediaError, match="формат видео"):
            video._check_container(data)


def test_probe_dimensions_uses_local_file_protocol_and_parses_dimensions(
    monkeypatch, tmp_path
):
    calls = []

    def fake_run(command, **kwargs):
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


def test_command_environment_rejects_missing_executable(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda name: None)

    with pytest.raises(FileNotFoundError, match="ffprobe"):
        video._command_environment("ffprobe")


def test_extract_video_rejects_resolution_before_running_ffmpeg(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
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


def test_extract_video_passes_resource_and_protocol_limits(monkeypatch):
    calls = []
    filter_scripts = []

    def fake_run(command, **kwargs):
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


# Content sniffing checks: the user-provided filename/MIME type is not trusted.
@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"GIF87a" + b"payload", "gif"),
        (b"GIF89a" + b"payload", "gif"),
        (b"\x1f\x8b" + b"payload", "tgs"),
        (b"\x1a\x45\xdf\xa3" + b"payload", "webm"),
        (b"\x00\x00\x00\x18ftypmp42" + b"payload", "mp4"),
        (b"\xff\xd8\xff" + b"payload", "image"),
        (b"\x89PNG\r\n\x1a\n" + b"payload", "image"),
        (b"RIFF\x00\x00\x00\x00WEBP" + b"payload", "image"),
        (b"BM" + b"payload", "image"),
        (b"II*\x00" + b"payload", "image"),
        (b"MM\x00*" + b"payload", "image"),
    ],
)
def test_sniff_media_type_recognizes_supported_signatures(data, expected):
    assert sniff_media_type(data) == expected


def test_sniff_media_type_rejects_unknown_or_short_mp4_data():
    assert sniff_media_type(b"not-a-media-file") is None
    assert sniff_media_type(b"\x00\x00\x00\x08ftyp") is None


@pytest.mark.parametrize(
    ("data", "declared"),
    [
        (b"GIF89a" + b"payload", "gif"),
        (b"\x1f\x8b" + b"payload", "tgs"),
        (b"\x89PNG\r\n\x1a\n" + b"payload", "image"),
        (b"\x1a\x45\xdf\xa3" + b"payload", "webm"),
        (b"\x00\x00\x00\x18ftypmp42" + b"payload", "mp4"),
        (b"\x1a\x45\xdf\xa3" + b"payload", "video"),
        # Telegram may report either MP4 or WEBM for supported video inputs.
        (b"\x1a\x45\xdf\xa3" + b"payload", "mp4"),
        (b"\x00\x00\x00\x18ftypmp42" + b"payload", "webm"),
    ],
)
def test_verify_declared_type_accepts_matching_types_and_video_family(data, declared):
    assert verify_declared_type(data, declared) is None


def test_verify_declared_type_rejects_mismatched_types():
    with pytest.raises(MediaError, match="не совпадает"):
        verify_declared_type(b"GIF89a" + b"payload", "mp4")

    with pytest.raises(MediaError, match="не совпадает"):
        verify_declared_type(b"\x89PNG\r\n\x1a\n" + b"payload", "tgs")

    with pytest.raises(MediaError, match="Неподдерживаемый"):
        verify_declared_type(b"not-a-media-file", "image")


@pytest.mark.asyncio
async def test_process_media_rejects_declared_type_mismatch_before_decoder():
    calls = []

    async def fake_download(message, file_id):
        return b"\x89PNG\r\n\x1a\n" + b"payload"

    async def fake_extract(data, media_type):
        calls.append((data, media_type))
        return [b"frame"]

    with pytest.raises(MediaError, match="не совпадает"):
        await media_pipeline.process_media(
            make_message(),
            "gif",
            "file-id",
            downloader=fake_download,
            animation_extractor=fake_extract,
            image_preparer=lambda data: "unused",
        )

    assert calls == []
