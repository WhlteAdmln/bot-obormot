# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for media pipeline."""

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services import media
from bot_obormot.services.media import pipeline as media_pipeline
from tests.support.media import make_message


@pytest.mark.asyncio
async def test_process_media_uses_canonical_media_dependencies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = make_message()
    calls = []

    async def fake_download(received_message: object, file_id: str) -> bytes:
        calls.append(("download", received_message, file_id))
        return b"GIF89a" + b"animation-data"

    async def fake_extract(data: object, media_type: str) -> list[object]:
        calls.append(("extract", data, media_type))
        return [b"frame-1", b"frame-2"]

    def fake_contact_sheet(frames: object) -> bytes:
        calls.append(("contact_sheet", frames))
        return b"combined-frames"

    def fake_prepare(image_data: object) -> str:
        calls.append(("prepare", image_data))
        return f"encoded:{image_data.decode()}"

    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)
    monkeypatch.setattr(media, "prepare_image", fake_prepare)

    result = await media_pipeline.process_media(
        message,
        "gif",
        "file-id",
        options=media_pipeline.MediaPipelineOptions(
            downloader=fake_download,
            animation_extractor=media.extract_animation_frames,
            image_preparer=media.prepare_image,
            contact_sheet_builder=fake_contact_sheet,
        ),
    )

    assert result == ["encoded:combined-frames"]
    assert calls[:3] == [
        ("download", message, "file-id"),
        ("extract", b"GIF89a" + b"animation-data", "gif"),
        ("contact_sheet", [b"frame-1", b"frame-2"]),
    ]
    assert calls[3] == ("prepare", b"combined-frames")


@pytest.mark.asyncio
async def test_process_media_wraps_unexpected_pipeline_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    async def fake_download(_message: object, _file_id: object) -> bytes:
        return b"GIF89a" + b"broken-animation"

    async def fake_extract(_data: object, _media_type: object) -> None:
        msg = "decoder failed"
        raise ValueError(msg)

    monkeypatch.setattr(media, "extract_animation_frames", fake_extract)

    with pytest.raises(MediaError, match="Failed to prepare gif media"):
        await media.process_media(
            make_message(), "gif", "file-id", downloader=fake_download
        )


@pytest.mark.asyncio
async def test_process_media_rejects_declared_type_mismatch_before_decoder() -> None:
    calls = []

    async def fake_download(_message: object, _file_id: object) -> bytes:
        return b"\x89PNG\r\n\x1a\n" + b"payload"

    async def fake_extract(data: object, media_type: str) -> list[object]:
        calls.append((data, media_type))
        return [b"frame"]

    with pytest.raises(MediaError, match="не совпадает"):
        await media_pipeline.process_media(
            make_message(),
            "gif",
            "file-id",
            options=media_pipeline.MediaPipelineOptions(
                downloader=fake_download,
                animation_extractor=fake_extract,
                image_preparer=lambda _data: "unused",
            ),
        )

    expected_empty = []
    assert calls == expected_empty, "expected an empty list"
