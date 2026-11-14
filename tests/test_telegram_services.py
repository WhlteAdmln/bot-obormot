# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for telegram services."""

import asyncio
from types import SimpleNamespace

import pytest

from bot.errors import MediaError
from bot.services import media
from bot.services.telegram import keep_typing
from bot.services.telegram.constants import MAX_CONCURRENT_DOWNLOADS
from bot.services.telegram.downloader import (
    _LimitedBytesIO,
    download_telegram_file,
)


class FakeBot:
    """Fake bot."""

    def __init__(
        self, *, file_size: object | None = None, data: bytes = b"telegram-file"
    ) -> None:
        """Initializes the test double."""
        self.file_size = file_size
        self.data = data
        self.download_calls = []

    async def get_file(self, file_id: str) -> SimpleNamespace:
        """Get file."""
        return SimpleNamespace(
            file_size=self.file_size,
            file_path=f"files/{file_id}",
        )

    async def download_file(self, file_path: object, destination: object) -> None:
        """Download file."""
        self.download_calls.append(file_path)
        destination.write(self.data)


def make_message(bot: object) -> SimpleNamespace:
    """Make message."""
    return SimpleNamespace(bot=bot)


@pytest.mark.parametrize(
    "data",
    [b"abc", bytearray(b"abc"), memoryview(b"abc")],
)
def test_limited_bytes_io_accepts_buffer_protocol(data: object) -> None:
    """Limited bytes io accepts buffer protocol."""
    buffer = _LimitedBytesIO(limit=3)

    assert buffer.write(data) == 3
    assert buffer.getvalue() == b"abc"


@pytest.mark.asyncio
async def test_telegram_downloader_returns_file_bytes() -> None:
    """Telegram downloader returns file bytes."""
    bot = FakeBot(file_size=13, data=b"hello, telegram")

    result = await download_telegram_file(make_message(bot), "file-id")

    assert result == b"hello, telegram"
    assert bot.download_calls == ["files/file-id"]


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_reported_oversized_file() -> None:
    """Telegram downloader rejects reported oversized file."""
    bot = FakeBot(file_size=media.MAX_MEDIA_SIZE + 1)

    with pytest.raises(MediaError, match="слишком большой"):
        await download_telegram_file(make_message(bot), "large-file")

    assert bot.download_calls == []


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_oversized_download_result() -> None:
    """Telegram downloader rejects oversized download result."""
    bot = FakeBot(file_size=10, data=b"x" * (media.MAX_MEDIA_SIZE + 1))

    with pytest.raises(MediaError, match="слишком большой"):
        await download_telegram_file(make_message(bot), "oversized-download")

    assert bot.download_calls == ["files/oversized-download"]


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_unknown_file_size() -> None:
    """Telegram downloader rejects unknown file size."""
    bot = FakeBot(file_size=None)

    with pytest.raises(MediaError, match="размер файла"):
        await download_telegram_file(make_message(bot), "unknown-size")

    assert bot.download_calls == []


@pytest.mark.asyncio
async def test_telegram_downloader_limits_concurrent_downloads() -> None:
    """Telegram downloader limits concurrent downloads."""

    class ConcurrentFakeBot(FakeBot):
        def __init__(self) -> None:
            super().__init__(file_size=3, data=b"abc")
            self.active_downloads = 0
            self.max_active_downloads = 0
            self.three_started = asyncio.Event()
            self.release_downloads = asyncio.Event()

        async def download_file(self, file_path: object, destination: object) -> None:
            self.download_calls.append(file_path)
            self.active_downloads += 1
            self.max_active_downloads = max(
                self.max_active_downloads,
                self.active_downloads,
            )
            if self.active_downloads == MAX_CONCURRENT_DOWNLOADS:
                self.three_started.set()

            try:
                await self.release_downloads.wait()
                destination.write(self.data)
            finally:
                self.active_downloads -= 1

    bot = ConcurrentFakeBot()
    tasks = [
        asyncio.create_task(download_telegram_file(make_message(bot), f"file-{index}"))
        for index in range(MAX_CONCURRENT_DOWNLOADS + 2)
    ]

    await asyncio.wait_for(bot.three_started.wait(), timeout=1)
    assert bot.active_downloads == MAX_CONCURRENT_DOWNLOADS
    assert bot.max_active_downloads == MAX_CONCURRENT_DOWNLOADS

    bot.release_downloads.set()
    results = await asyncio.gather(*tasks)

    assert results == [b"abc"] * (MAX_CONCURRENT_DOWNLOADS + 2)
    assert bot.max_active_downloads == MAX_CONCURRENT_DOWNLOADS


def test_telegram_services_are_imported_from_canonical_modules() -> None:
    """Telegram services are imported from canonical modules."""
    assert media.download_telegram_file is download_telegram_file
    assert keep_typing.__module__ == "bot.services.telegram.chat_action"
