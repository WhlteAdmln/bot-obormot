# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for telegram downloader."""

import asyncio

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services import media
from bot_obormot.services.telegram.constants import MAX_CONCURRENT_DOWNLOADS
from bot_obormot.services.telegram.downloader import download_telegram_file
from tests.support.telegram_downloads import FakeDownloadBot, make_message


@pytest.mark.parametrize(
    "data",
    [b"abc", bytearray(b"abc"), memoryview(b"abc")],
)
@pytest.mark.asyncio
async def test_downloader_accepts_any_buffer_protocol_payload(data: object) -> None:
    bot = FakeDownloadBot(file_size=3, data=data)
    result = await download_telegram_file(make_message(bot), "buffer")
    expected = b"abc"
    assert result == expected, "every bytes-like payload must be stored"


@pytest.mark.asyncio
async def test_telegram_downloader_returns_file_bytes() -> None:
    """Telegram downloader returns file bytes."""
    bot = FakeDownloadBot(file_size=13, data=b"hello, telegram")

    result = await download_telegram_file(make_message(bot), "file-id")

    expected_result = b"hello, telegram"
    assert result == expected_result
    assert bot.download_calls == ["files/file-id"]


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_reported_oversized_file() -> None:
    """Telegram downloader rejects reported oversized file."""
    bot = FakeDownloadBot(file_size=media.MAX_MEDIA_SIZE + 1)

    with pytest.raises(MediaError, match="слишком большой"):
        await download_telegram_file(make_message(bot), "large-file")

    assert not bot.download_calls


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_oversized_download_result() -> None:
    """Telegram downloader rejects oversized download result."""
    bot = FakeDownloadBot(file_size=10, data=b"x" * (media.MAX_MEDIA_SIZE + 1))

    with pytest.raises(MediaError, match="слишком большой"):
        await download_telegram_file(make_message(bot), "oversized-download")

    assert bot.download_calls == ["files/oversized-download"]


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_unknown_file_size() -> None:
    """Telegram downloader rejects unknown file size."""
    bot = FakeDownloadBot(file_size=None)

    with pytest.raises(MediaError, match="размер файла"):
        await download_telegram_file(make_message(bot), "unknown-size")

    assert not bot.download_calls


@pytest.mark.asyncio
async def test_telegram_downloader_limits_concurrent_downloads() -> None:
    """Telegram downloader limits concurrent downloads."""
    bot = FakeDownloadBot(file_size=3, data=b"abc", hold=True)
    tasks = [
        asyncio.create_task(download_telegram_file(make_message(bot), f"file-{index}"))
        for index in range(MAX_CONCURRENT_DOWNLOADS + 2)
    ]

    await asyncio.wait_for(bot.wait_for_active(MAX_CONCURRENT_DOWNLOADS), timeout=1)
    assert bot.active_downloads == MAX_CONCURRENT_DOWNLOADS
    assert bot.max_active_downloads == MAX_CONCURRENT_DOWNLOADS

    bot.release.set()
    results = await asyncio.gather(*tasks)

    assert results == [b"abc"] * (MAX_CONCURRENT_DOWNLOADS + 2)
    assert bot.max_active_downloads == MAX_CONCURRENT_DOWNLOADS
