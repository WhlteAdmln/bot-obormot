# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media detection, image preparation, content and concurrency."""

import asyncio
import base64
import io
import threading
from types import SimpleNamespace

import pytest
from PIL import Image

from bot_obormot.errors import MediaError
from bot_obormot.services.media import content as media_content
from bot_obormot.services.media import images as media_images
from bot_obormot.services.media.animation.concurrency import extract_with_limit
from bot_obormot.services.media.detection import get_media_info


def make_media_message(**overrides: object) -> SimpleNamespace:
    """Create a message with empty media fields."""
    values: dict[str, object] = {
        "photo": None,
        "animation": None,
        "video": None,
        "sticker": None,
        "document": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            make_media_message(photo=[SimpleNamespace(file_id="photo-id")]),
            ("photo-id", "image"),
        ),
        (
            make_media_message(
                animation=SimpleNamespace(file_id="animation-id"),
            ),
            ("animation-id", "mp4"),
        ),
        (
            make_media_message(video=SimpleNamespace(file_id="video-id")),
            ("video-id", "mp4"),
        ),
        (
            make_media_message(
                sticker=SimpleNamespace(
                    file_id="animated-id",
                    is_animated=True,
                    is_video=False,
                ),
            ),
            ("animated-id", "tgs"),
        ),
        (
            make_media_message(
                sticker=SimpleNamespace(
                    file_id="video-sticker-id",
                    is_animated=False,
                    is_video=True,
                ),
            ),
            ("video-sticker-id", "webm"),
        ),
        (
            make_media_message(
                sticker=SimpleNamespace(
                    file_id="static-sticker-id",
                    is_animated=False,
                    is_video=False,
                ),
            ),
            ("static-sticker-id", "image"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="gif-name",
                    file_name="IMAGE.GIF",
                    mime_type="application/octet-stream",
                ),
            ),
            ("gif-name", "gif"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="gif-mime",
                    file_name="image.bin",
                    mime_type="IMAGE/GIF",
                ),
            ),
            ("gif-mime", "gif"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="webm-name",
                    file_name="clip.WEBM",
                    mime_type=None,
                ),
            ),
            ("webm-name", "webm"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="webm-mime",
                    file_name="clip.bin",
                    mime_type="video/webm",
                ),
            ),
            ("webm-mime", "webm"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="mp4-name",
                    file_name="clip.MP4",
                    mime_type=None,
                ),
            ),
            ("mp4-name", "mp4"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="mp4-mime",
                    file_name="clip.bin",
                    mime_type="video/mp4",
                ),
            ),
            ("mp4-mime", "mp4"),
        ),
        (
            make_media_message(
                document=SimpleNamespace(
                    file_id="unknown-id",
                    file_name="report.pdf",
                    mime_type="application/pdf",
                ),
            ),
            (None, None),
        ),
        (make_media_message(), (None, None)),
    ],
)
def test_get_media_info_detects_message_media(
    message: SimpleNamespace,
    expected: tuple[str | None, str | None],
) -> None:
    """Detect media types from message fields and document metadata."""
    assert get_media_info(message) == expected


def encode_image(image: Image.Image, image_format: str = "PNG") -> bytes:
    """Encode a Pillow image into an in-memory file."""
    output = io.BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_prepare_image_rejects_oversized_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject an image exceeding the application pixel limit."""
    monkeypatch.setattr(media_images, "MAX_IMAGE_PIXELS", 5)
    image_data = encode_image(Image.new("RGB", (3, 2)))

    with pytest.raises(MediaError, match="слишком большое"):
        media_images.prepare_image(image_data)


def test_prepare_image_respects_pillow_decompression_bomb_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject an image exceeding Pillow's decompression warning threshold."""
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 5)
    image_data = encode_image(Image.new("RGB", (3, 2)))

    with pytest.raises(Image.DecompressionBombWarning):
        media_images.prepare_image(image_data)


def test_prepare_image_rejects_corrupt_file() -> None:
    """Propagate Pillow's error for an unrecognized image."""
    with pytest.raises(Image.UnidentifiedImageError):
        media_images.prepare_image(b"not-an-image")


def test_prepare_image_applies_exif_rotation() -> None:
    """Apply EXIF orientation before converting the image."""
    source = Image.new("RGB", (4, 2), "red")
    exif = Image.Exif()
    exif[274] = 6
    output = io.BytesIO()
    source.save(output, format="JPEG", exif=exif)

    result = media_images.prepare_image(output.getvalue())
    encoded = result.split(",", 1)[1]
    decoded = base64.b64decode(encoded)
    with Image.open(io.BytesIO(decoded)) as image:
        assert image.format == "JPEG"
        assert image.size == (2, 4)


@pytest.mark.parametrize(
    ("mode", "color"),
    [
        ("RGBA", (255, 0, 0, 0)),
        ("LA", (128, 0)),
    ],
)
def test_prepare_image_composites_alpha_channels(
    mode: str,
    color: tuple[int, ...],
) -> None:
    """Composite transparent RGBA and LA images onto a white background."""
    image_data = encode_image(Image.new(mode, (2, 2), color))
    result = media_images.prepare_image(image_data)
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        assert image.mode == "RGB"
        assert min(image.getpixel((0, 0))) >= 245


def test_prepare_image_handles_palette_transparency() -> None:
    """Composite palette images with a transparent palette entry."""
    source = Image.new("P", (2, 2), 0)
    source.putpalette([255, 0, 0, 0, 0, 0] + [0] * 762)
    output = io.BytesIO()
    source.save(output, format="PNG", transparency=0)

    result = media_images.prepare_image(output.getvalue())
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        assert image.mode == "RGB"
        assert min(image.getpixel((0, 0))) >= 245


def test_prepare_image_converts_rgb_and_resizes_large_dimensions() -> None:
    """Convert opaque images to RGB and apply the maximum dimension."""
    image_data = encode_image(Image.new("RGB", (1600, 800), (20, 40, 60)))

    result = media_images.prepare_image(image_data)
    decoded = base64.b64decode(result.split(",", 1)[1])
    with Image.open(io.BytesIO(decoded)) as image:
        assert image.format == "JPEG"
        assert image.mode == "RGB"
        assert image.size == (1536, 768)


@pytest.mark.parametrize(
    ("image_urls", "media_type", "expected_fragment"),
    [
        (
            ["data:image/jpeg;base64,AA=="],
            "tgs",
            "одно нумерованное изображение-монтаж",
        ),
        (
            [
                "data:image/jpeg;base64,AA==",
                "data:image/jpeg;base64,AQ==",
            ],
            "image",
            "Кадры расположены в хронологическом порядке",
        ),
        (
            ["data:image/jpeg;base64,AA=="],
            "image",
            None,
        ),
    ],
)
def test_get_user_content_formats_media_prompts(
    monkeypatch: pytest.MonkeyPatch,
    image_urls: list[str],
    media_type: str,
    expected_fragment: str | None,
) -> None:
    """Add animation guidance only for animations or multiple frames."""
    monkeypatch.setattr(
        media_content,
        "get_media_prompt",
        lambda _message, _media_type: "Prompt",
    )

    result = media_content.get_user_content(
        SimpleNamespace(text="plain text"),
        image_urls,
        media_type,
    )

    assert isinstance(result, list)
    assert result[0]["text"].startswith("Prompt")
    assert [part["image_url"]["url"] for part in result[1:]] == image_urls
    if expected_fragment is not None:
        assert expected_fragment in result[0]["text"]
    else:
        assert result[0]["text"] == "Prompt"


@pytest.mark.parametrize("image_urls", [None, []])
def test_get_user_content_returns_plain_text_without_images(
    image_urls: list[str] | None,
) -> None:
    """Return the original message text when there are no images."""
    message = SimpleNamespace(text="plain text")

    assert media_content.get_user_content(message, image_urls, "image") == "plain text"


@pytest.mark.asyncio
async def test_extract_with_limit_uses_default_semaphore() -> None:
    """Use the module semaphore when no explicit semaphore is supplied."""

    def extractor(data: bytes, media_type: str) -> list[bytes]:
        return [data + media_type.encode("ascii")]

    result = await extract_with_limit(b"data", "gif", extractor)

    assert result == [b"datagif"]


@pytest.mark.asyncio
async def test_extract_with_limit_respects_semaphore_capacity() -> None:
    """Keep the number of concurrent extractors within semaphore capacity."""
    semaphore = asyncio.Semaphore(2)
    guard = threading.Lock()
    both_started = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0

    def extractor(data: bytes, _media_type: str) -> list[bytes]:
        nonlocal active, maximum
        with guard:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                both_started.set()
        try:
            if not release.wait(5):
                msg = "Extractor was not released"
                raise TimeoutError(msg)
            return [data]
        finally:
            with guard:
                active -= 1

    tasks = [
        asyncio.create_task(
            extract_with_limit(
                str(index).encode("ascii"),
                "gif",
                extractor,
                semaphore,
            )
        )
        for index in range(4)
    ]

    assert await asyncio.to_thread(both_started.wait, 2)
    assert maximum == 2
    release.set()

    results = await asyncio.gather(*tasks)

    assert results == [[b"0"], [b"1"], [b"2"], [b"3"]]
    assert maximum == 2


@pytest.mark.asyncio
async def test_cancelled_extractor_holds_semaphore_until_thread_finishes() -> None:
    """Do not release the semaphore while a cancelled worker is still running."""
    semaphore = asyncio.Semaphore(1)
    first_started = threading.Event()
    second_started = threading.Event()
    release_first = threading.Event()

    def first_extractor(data: bytes, _media_type: str) -> list[bytes]:
        first_started.set()
        if not release_first.wait(5):
            msg = "First extractor was not released"
            raise TimeoutError(msg)
        return [data]

    def second_extractor(data: bytes, _media_type: str) -> list[bytes]:
        second_started.set()
        return [data]

    first_task = asyncio.create_task(
        extract_with_limit(b"first", "gif", first_extractor, semaphore)
    )
    assert await asyncio.to_thread(first_started.wait, 2)

    first_task.cancel()
    second_task = asyncio.create_task(
        extract_with_limit(b"second", "gif", second_extractor, semaphore)
    )
    await asyncio.sleep(0)

    assert not second_started.is_set()
    release_first.set()

    with pytest.raises(asyncio.CancelledError):
        await first_task

    assert await second_task == [b"second"]
    assert second_started.is_set()
