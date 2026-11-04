from types import SimpleNamespace

import pytest

from bot.errors import MediaError
from bot.services import media
from bot.services.chat_actions import keep_typing as legacy_keep_typing
from bot.services.telegram import keep_typing
from bot.services.telegram.downloader import download_telegram_file


class FakeBot:
    def __init__(self, *, file_size=None, data=b"telegram-file"):
        self.file_size = file_size
        self.data = data
        self.download_calls = []

    async def get_file(self, file_id):
        return SimpleNamespace(
            file_size=self.file_size,
            file_path=f"files/{file_id}",
        )

    async def download_file(self, file_path, destination):
        self.download_calls.append(file_path)
        destination.write(self.data)


def make_message(bot):
    return SimpleNamespace(bot=bot)


@pytest.mark.asyncio
async def test_telegram_downloader_returns_file_bytes():
    bot = FakeBot(file_size=13, data=b"hello, telegram")

    result = await download_telegram_file(make_message(bot), "file-id")

    assert result == b"hello, telegram"
    assert bot.download_calls == ["files/file-id"]


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_reported_oversized_file():
    bot = FakeBot(file_size=media.MAX_MEDIA_SIZE + 1)

    with pytest.raises(MediaError, match="слишком большой"):
        await download_telegram_file(make_message(bot), "large-file")

    assert bot.download_calls == []


@pytest.mark.asyncio
async def test_telegram_downloader_rejects_oversized_download_result():
    bot = FakeBot(data=b"x" * (media.MAX_MEDIA_SIZE + 1))

    with pytest.raises(MediaError, match="слишком большой"):
        await download_telegram_file(make_message(bot), "unreported-large-file")

    assert bot.download_calls == ["files/unreported-large-file"]


def test_legacy_import_paths_remain_available():
    assert media.download_telegram_file is download_telegram_file
    assert legacy_keep_typing is keep_typing
