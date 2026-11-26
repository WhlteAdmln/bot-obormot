# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input media part."""

from __future__ import annotations

import base64

import pytest

from bot_obormot.services.chat.input import media_part as media_module
from bot_obormot.services.media.slots import MediaSlots
from tests.support.message_input import make_info, make_message


def _data_url(image: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")


@pytest.mark.asyncio
async def test_prepare_media_passes_the_media_to_the_processor() -> None:
    file_id = "AgACAgIAAxkBAAIB-photo"
    received: list[object] = []
    media_slots = MediaSlots()

    async def download(_message: object, _file_id: str) -> bytes:
        return b"\xff\xd8\xff"

    async def process(
        _message: object,
        media_type: str,
        actual_file_id: str,
        *,
        downloader: object,
        slots: object,
    ) -> list[object]:
        received.append((media_type, actual_file_id, downloader, slots))
        return [_data_url(b"\xff\xd8\xff")]

    info = make_info(file_id=file_id, media_type="image", has_media=True)
    await media_module.prepare_media(
        make_message(),
        info,
        downloader=download,
        media_slots=media_slots,
        media_processor=process,
    )
    expected = [("image", file_id, download, media_slots)]
    assert received == expected, "the processor got other media arguments"


@pytest.mark.asyncio
async def test_prepare_media_returns_the_data_urls() -> None:
    data_url = _data_url(b"image-data")

    async def download(_message: object, _file_id: str) -> bytes:
        return b"image-data"

    async def process(
        _message: object,
        _media_type: str,
        _file_id: str,
        *,
        downloader: object,
        slots: object,
    ) -> list[object]:
        del downloader, slots
        return [data_url]

    info = make_info(file_id="image-id", media_type="image", has_media=True)
    urls, _image_bytes = await media_module.prepare_media(
        make_message(),
        info,
        downloader=download,
        media_slots=MediaSlots(),
        media_processor=process,
    )
    assert urls == [data_url], "the data urls were not returned"


@pytest.mark.asyncio
async def test_prepare_media_decodes_data_urls_to_original_image_bytes() -> None:
    image = b"\x89PNG\r\n\x1a\nchart"
    data_url = _data_url(image)

    async def download(_message: object, _file_id: str) -> bytes:
        return image

    async def process(
        _message: object,
        _media_type: str,
        _file_id: str,
        *,
        downloader: object,
        slots: object,
    ) -> list[object]:
        del downloader, slots
        return [data_url]

    info = make_info(file_id="chart-id", media_type="image", has_media=True)
    _urls, image_bytes = await media_module.prepare_media(
        make_message(),
        info,
        downloader=download,
        media_slots=MediaSlots(),
        media_processor=process,
    )
    assert image_bytes == [image], "the data url was not decoded to the image bytes"
