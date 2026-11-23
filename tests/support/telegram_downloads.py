# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""A fake Telegram bot for file download tests."""

import asyncio
from types import SimpleNamespace


class FakeDownloadBot:
    """Serve one file and record downloads; optionally hold them until released."""

    def __init__(
        self,
        *,
        file_size: object | None = None,
        data: object = b"telegram-file",
        hold: bool = False,
    ) -> None:
        """Store the declared size, the payload and whether to hold downloads."""
        self.file_size = file_size
        self.data = data
        self.download_calls: list[object] = []
        self.active_downloads = 0
        self.max_active_downloads = 0
        self.release = asyncio.Event()
        if not hold:
            self.release.set()
        self._changed = asyncio.Condition()

    async def get_file(self, file_id: str) -> SimpleNamespace:
        """Describe the file with the configured size."""
        return SimpleNamespace(file_size=self.file_size, file_path=f"files/{file_id}")

    async def download_file(self, file_path: object, destination: object) -> None:
        """Write the payload once the download is released."""
        self.download_calls.append(file_path)
        async with self._changed:
            self.active_downloads += 1
            self.max_active_downloads = max(
                self.max_active_downloads, self.active_downloads
            )
            self._changed.notify_all()
        try:
            await self.release.wait()
        finally:
            self.active_downloads -= 1
        destination.write(self.data)

    async def wait_for_active(self, count: int) -> None:
        """Wait until ``count`` downloads run at the same time."""
        async with self._changed:
            await self._changed.wait_for(lambda: self.active_downloads >= count)


def make_message(bot: object) -> SimpleNamespace:
    """Make a message that belongs to the given bot."""
    return SimpleNamespace(bot=bot)
