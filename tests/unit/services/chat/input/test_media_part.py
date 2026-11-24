# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input media part."""

from __future__ import annotations

import base64

import pytest

from bot_obormot.services.chat.input import media_part as media_module
from tests.support.message_input import make_info, make_message


@pytest.mark.asyncio
async def test_prepare_media_decodes_data_urls_to_original_image_bytes() -> None:
    image = b"image-data"
    data_url = "data:image/jpeg;base64," + base64.b64encode(image).decode("ascii")

    async def process(_message: object, media_type: str, file_id: str) -> list[object]:
        assert (media_type, file_id) == ("image", "image-id")
        return [data_url]

    info = make_info(file_id="image-id", media_type="image", has_media=True)
    urls, image_bytes = await media_module.prepare_media(
        make_message(),
        info,
        media_processor=process,
    )

    assert urls == [data_url]
    assert image_bytes == [image]
