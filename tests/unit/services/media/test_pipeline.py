# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media pipeline."""

import asyncio
import threading

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services import media
from bot_obormot.services.media import pipeline as media_pipeline
from bot_obormot.services.media.slots import MediaSlots
from tests.support.media import make_message


async def run_gif_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    message: object,
    file_id: str,
    payload: bytes,
    frames: list[bytes],
) -> tuple[list[str], list[tuple[object, ...]]]:
    """Run a gif through the pipeline with recording fakes."""
    calls: list[tuple[object, ...]] = []

    async def fake_download(received_message: object, received_id: str) -> bytes:
        calls.append(("download", received_message, received_id))
        return payload

    async def fake_extract(
        data: object, media_type: str, _semaphore: object
    ) -> list[bytes]:
        calls.append(("extract", data, media_type))
        return frames

    def fake_contact_sheet(received_frames: list[bytes]) -> bytes:
        calls.append(("contact_sheet", received_frames))
        return b"|".join(received_frames)

    def fake_prepare(image_data: bytes) -> str:
        calls.append(("prepare", image_data))
        return f"encoded:{image_data.decode()}"

    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)
    monkeypatch.setattr(media, "prepare_image", fake_prepare)

    result = await media_pipeline.process_media(
        message,
        "gif",
        file_id,
        options=media_pipeline.MediaPipelineOptions(
            downloader=fake_download,
            slots=MediaSlots(),
            animation_extractor=media.extract_animation_frames,
            image_preparer=media.prepare_image,
            contact_sheet_builder=fake_contact_sheet,
        ),
    )
    return result, calls


@pytest.mark.asyncio
async def test_process_media_returns_the_prepared_contact_sheet(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"GIF89a" + b"animation-data"
    frames = [b"frame-1", b"frame-2"]
    result, _calls = await run_gif_pipeline(
        monkeypatch, make_message(), "file-id", payload, frames
    )
    expected = ["encoded:frame-1|frame-2"]
    assert result == expected, "the prepared contact sheet was not returned"


@pytest.mark.asyncio
async def test_process_media_downloads_extracts_and_combines_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = make_message(caption="looping cat")
    payload = b"GIF87a" + b"cat-loop-29"
    frames = [b"paw", b"tail", b"ear"]
    _result, calls = await run_gif_pipeline(
        monkeypatch, message, "BQACAgIAAx0", payload, frames
    )
    expected = [
        ("download", message, "BQACAgIAAx0"),
        ("extract", payload, "gif"),
        ("contact_sheet", frames),
    ]
    assert calls[:3] == expected, "the pipeline steps ran out of order"


@pytest.mark.asyncio
async def test_process_media_prepares_the_combined_frames(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"GIF89a" + b"rain-drops"
    frames = [b"drop-a", b"drop-b"]
    _result, calls = await run_gif_pipeline(
        monkeypatch, make_message(), "CgACAgUAAxk", payload, frames
    )
    expected = ("prepare", b"drop-a|drop-b")
    assert calls[3] == expected, "the combined frames were not prepared"


@pytest.mark.asyncio
async def test_process_media_wraps_unexpected_pipeline_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    async def fake_download(_message: object, _file_id: object) -> bytes:
        return b"GIF89a" + b"broken-animation"

    async def fake_extract(
        _data: object, _media_type: object, _semaphore: object
    ) -> None:
        msg = "decoder failed"
        raise ValueError(msg)

    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)

    expected = "Failed to prepare gif media"
    with pytest.raises(MediaError, match="Failed to prepare") as caught:
        await media.process_media(
            make_message(),
            "gif",
            "file-id",
            downloader=fake_download,
            slots=MediaSlots(),
        )
    assert str(caught.value) == expected, "the decoder error was not wrapped"


@pytest.mark.asyncio
async def test_process_media_rejects_declared_type_mismatch_before_decoder() -> None:
    calls: list[tuple[object, str]] = []

    async def fake_download(_message: object, _file_id: object) -> bytes:
        return b"\x89PNG\r\n\x1a\n" + b"payload"

    async def fake_extract(
        data: object, media_type: str, _semaphore: object
    ) -> list[object]:
        calls.append((data, media_type))
        return [b"frame"]

    with pytest.raises(MediaError, match="не совпадает"):
        await media_pipeline.process_media(
            make_message(),
            "gif",
            "file-id",
            options=media_pipeline.MediaPipelineOptions(
                downloader=fake_download,
                slots=MediaSlots(),
                animation_extractor=fake_extract,
                image_preparer=lambda _data: "unused",
            ),
        )

    expected_empty: list[tuple[object, str]] = []
    assert calls == expected_empty, "expected an empty list"


@pytest.mark.asyncio
async def test_holds_an_image_job_slot_while_preparing_an_image() -> None:
    slots = MediaSlots(image_jobs=asyncio.Semaphore(1))
    started = threading.Event()
    release = threading.Event()
    payload = b"\xff\xd8\xff\xe0" + b"jfif-body-17"

    async def fake_download(_message: object, _file_id: str) -> bytes:
        return payload

    def blocking_prepare(_data: bytes) -> str:
        started.set()
        release.wait(5)
        return "data:image/jpeg;base64,/9j/"

    task = asyncio.create_task(
        media_pipeline.process_media(
            make_message(),
            "image",
            "AgADBAADr6cxG",
            options=media_pipeline.MediaPipelineOptions(
                downloader=fake_download,
                slots=slots,
                image_preparer=blocking_prepare,
            ),
        )
    )
    await asyncio.to_thread(started.wait, 2)
    locked_while_preparing = slots.image_jobs.locked()
    release.set()
    await task

    assert locked_while_preparing, "image preparation must hold an image job slot"


@pytest.mark.asyncio
async def test_passes_the_animation_slots_to_the_extractor() -> None:
    slots = MediaSlots(animations=asyncio.Semaphore(4))
    received = []

    async def fake_download(_message: object, _file_id: str) -> bytes:
        return b"GIF87a" + b"tiny-loop"

    async def fake_extract(
        _data: bytes, _media_type: str, semaphore: asyncio.Semaphore
    ) -> list[bytes]:
        received.append(semaphore)
        return [b"frame-a"]

    await media_pipeline.process_media(
        make_message(),
        "gif",
        "CgACAgQAAxkB",
        options=media_pipeline.MediaPipelineOptions(
            downloader=fake_download,
            slots=slots,
            animation_extractor=fake_extract,
            image_preparer=lambda _data: "data:image/jpeg;base64,AQID",
            contact_sheet_builder=lambda frames: frames[0],
        ),
    )

    expected = [slots.animations]
    assert received == expected, "the extractor must get the animation slots"
