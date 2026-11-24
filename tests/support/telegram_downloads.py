# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""A fake Telegram bot for file download tests."""

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace


@dataclass
class DownloadActivity:
    """Downloads running now and the most that ran at the same time."""

    current: int = 0
    peak: int = 0


class FakeDownloadBot:
    """Serve one file and record downloads; optionally hold them until released."""

    def __init__(
        self,
        *,
        file_size: object | None = None,
        data: object = b"telegram-file",
        hold: bool = False,
        error: Exception | None = None,
    ) -> None:
        """Store the size, the payload, whether to hold and an error to raise."""
        self.file_size = file_size
        self.error = error
        self.data = data
        self.download_calls: list[object] = []
        self.activity = DownloadActivity()
        self.release = asyncio.Event()
        if not hold:
            self.release.set()
        self._changed = asyncio.Condition()

    async def get_file(self, file_id: str) -> SimpleNamespace:
        """Raise the configured error or describe the file with its size."""
        if self.error is not None:
            raise self.error
        return SimpleNamespace(file_size=self.file_size, file_path=f"files/{file_id}")

    async def download_file(self, file_path: object, destination: object) -> None:
        """Write the payload once the download is released."""
        self.download_calls.append(file_path)
        async with self._changed:
            self.activity.current += 1
            self.activity.peak = max(self.activity.peak, self.activity.current)
            self._changed.notify_all()
        try:
            await self.release.wait()
        finally:
            self.activity.current -= 1
        destination.write(self.data)

    async def wait_for_active(self, count: int) -> None:
        """Wait until ``count`` downloads run at the same time."""
        async with self._changed:
            await self._changed.wait_for(lambda: self.activity.current >= count)


def make_message(bot: object) -> SimpleNamespace:
    """Make a message that belongs to the given bot."""
    return SimpleNamespace(bot=bot)
