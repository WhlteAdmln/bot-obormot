import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from bot.errors import MediaError
from bot.services import animation, media
from bot.services.media.animation.sampling import sample_frame_indices


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


def test_get_user_content_preserves_frame_order_and_adds_sequence_note():
    message = make_message(caption=None, sticker=None, text="ignored")
    urls = ["data:image/jpeg;base64,first", "data:image/jpeg;base64,second"]

    content = media.get_user_content(message, urls, "gif")

    assert content[0]["type"] == "text"
    assert "хронологическом порядке" in content[0]["text"]
    assert [part["image_url"]["url"] for part in content[1:]] == urls


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


def test_dispatcher_routes_formats_and_preserves_legacy_patch_points(monkeypatch):
    calls = []
    monkeypatch.setattr(
        animation, "_extract_gif", lambda data: calls.append(("gif", data)) or [b"g"]
    )
    monkeypatch.setattr(
        animation, "_extract_tgs", lambda data: calls.append(("tgs", data)) or [b"t"]
    )
    monkeypatch.setattr(
        animation, "_extract_webm", lambda data: calls.append(("video", data)) or [b"v"]
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
async def test_process_media_uses_legacy_package_level_dependencies(monkeypatch):
    message = make_message()
    calls = []

    async def fake_download(received_message, file_id):
        calls.append(("download", received_message, file_id))
        return b"animation-data"

    async def fake_extract(data, media_type):
        calls.append(("extract", data, media_type))
        return [b"frame-1", b"frame-2"]

    def fake_prepare(frame):
        calls.append(("prepare", frame))
        return f"encoded:{frame.decode()}"

    monkeypatch.setattr(media, "download_telegram_file", fake_download)
    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)
    monkeypatch.setattr(media, "prepare_image", fake_prepare)

    result = await media.process_media(message, "gif", "file-id")

    assert result == ["encoded:frame-1", "encoded:frame-2"]
    assert calls[:2] == [
        ("download", message, "file-id"),
        ("extract", b"animation-data", "gif"),
    ]
    assert {call[1] for call in calls if call[0] == "prepare"} == {
        b"frame-1",
        b"frame-2",
    }


@pytest.mark.asyncio
async def test_animation_dispatch_errors_are_wrapped_as_media_error():
    with pytest.raises(MediaError, match="Failed to process unknown animation"):
        await animation.extract_animation_frames(b"data", "unknown")


def test_extract_gif_returns_at_most_six_jpeg_frames():
    from bot.services.media.animation.gif import extract_gif

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
        return b"broken-animation"

    async def fake_extract(data, media_type):
        raise ValueError("decoder failed")

    monkeypatch.setattr(media, "download_telegram_file", fake_download)
    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)

    with pytest.raises(MediaError, match="Failed to prepare gif media"):
        await media.process_media(make_message(), "gif", "file-id")
