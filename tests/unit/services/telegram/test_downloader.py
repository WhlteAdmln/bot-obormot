# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for telegram downloader."""

import asyncio

import pytest
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.methods import GetFile

from bot_obormot.errors import AppError
from bot_obormot.services import media
from bot_obormot.services.telegram.constants import MAX_CONCURRENT_DOWNLOADS
from bot_obormot.services.telegram.downloader import TelegramDownloader
from tests.support.telegram_downloads import FakeDownloadBot, make_message


async def _failure(bot: FakeDownloadBot, file_id: str) -> tuple[str, str]:
    try:
        await TelegramDownloader()(make_message(bot), file_id)
    except AppError as error:
        return error.code, str(error)
    return "", ""


async def _concurrency_trace(count: int) -> tuple[int, int, list[bytes]]:
    bot = FakeDownloadBot(file_size=3, data=b"abc", hold=True)
    downloader = TelegramDownloader()
    tasks = [
        asyncio.create_task(downloader(make_message(bot), f"file-{index}"))
        for index in range(count)
    ]
    await asyncio.wait_for(bot.wait_for_active(MAX_CONCURRENT_DOWNLOADS), timeout=1)
    active = bot.activity.current
    bot.release.set()
    results = await asyncio.gather(*tasks)
    return active, bot.activity.peak, results


@pytest.mark.parametrize(
    "data",
    [b"abc", bytearray(b"abc"), memoryview(b"abc")],
)
@pytest.mark.asyncio
async def test_downloader_accepts_any_buffer_protocol_payload(data: object) -> None:
    bot = FakeDownloadBot(file_size=3, data=data)
    result = await TelegramDownloader()(make_message(bot), "buffer")
    expected = b"abc"
    assert result == expected, "every bytes-like payload must be stored"


@pytest.mark.asyncio
async def test_returns_the_file_bytes() -> None:
    bot = FakeDownloadBot(file_size=15, data=b"hello, telegram")
    result = await TelegramDownloader()(make_message(bot), "file-id")
    expected = b"hello, telegram"
    assert result == expected, "the downloaded bytes are wrong"


@pytest.mark.asyncio
async def test_downloads_the_path_telegram_reported() -> None:
    bot = FakeDownloadBot(file_size=13, data=b"hello, telegram")
    await TelegramDownloader()(make_message(bot), "AgACAgIAAxkBAAI")
    expected = ["files/AgACAgIAAxkBAAI"]
    assert bot.download_calls == expected, "the wrong file path was downloaded"


@pytest.mark.asyncio
async def test_accepts_a_file_of_exactly_the_maximum_size() -> None:
    data = b"z" * media.MAX_MEDIA_SIZE
    bot = FakeDownloadBot(file_size=media.MAX_MEDIA_SIZE, data=data)
    result = await TelegramDownloader()(make_message(bot), "edge")
    assert len(result) == media.MAX_MEDIA_SIZE, "a file at the limit must be kept"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("file_size", "expected"),
    [
        (media.MAX_MEDIA_SIZE + 1, "Файл слишком большой (максимум 20 МБ)."),
        (2**63, "Файл слишком большой (максимум 20 МБ)."),
        (None, "Не удалось определить размер файла."),
        (0, "Не удалось определить размер файла."),
        (-1, "Не удалось определить размер файла."),
        (True, "Не удалось определить размер файла."),
        ("10", "Не удалось определить размер файла."),
        (3.5, "Не удалось определить размер файла."),
    ],
    ids=["one-over", "huge", "unknown", "zero", "negative", "bool", "string", "float"],
)
async def test_rejects_a_bad_reported_size(file_size: object, expected: str) -> None:
    bot = FakeDownloadBot(file_size=file_size)
    failure = ("media_error", expected)
    assert await _failure(bot, "reported") == failure, "the size must be rejected"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "file_size",
    [media.MAX_MEDIA_SIZE + 1, None, 0],
    ids=["oversized", "unknown", "zero"],
)
async def test_does_not_download_a_file_with_a_bad_reported_size(
    file_size: object,
) -> None:
    bot = FakeDownloadBot(file_size=file_size)
    await _failure(bot, "never-fetched")
    expected_empty: list[object] = []
    assert bot.download_calls == expected_empty, "a refused file was downloaded"


@pytest.mark.asyncio
async def test_rejects_a_download_larger_than_the_reported_size() -> None:
    bot = FakeDownloadBot(file_size=10, data=b"x" * (media.MAX_MEDIA_SIZE + 1))
    expected = ("media_error", "Файл слишком большой (максимум 20 МБ).")
    assert await _failure(bot, "liar") == expected, "the oversized body must be refused"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (
            TelegramBadRequest(GetFile(file_id="big"), "Bad Request: file is too big"),
            (
                "telegram_file_too_big",
                "Telegram cannot download this file because it is too large",
            ),
        ),
        (
            TelegramBadRequest(GetFile(file_id="gone"), "Bad Request: invalid file_id"),
            ("telegram_error", "Could not download file from Telegram"),
        ),
        (
            TelegramAPIError(GetFile(file_id="down"), "Internal Server Error"),
            ("telegram_error", "Could not download file from Telegram"),
        ),
    ],
    ids=["too-big", "bad-request", "api-error"],
)
async def test_translates_a_telegram_failure(
    error: Exception, expected: tuple[str, str]
) -> None:
    bot = FakeDownloadBot(error=error)
    assert await _failure(bot, "broken") == expected, "the failure is not translated"


@pytest.mark.asyncio
async def test_queues_downloads_over_the_limit_and_finishes_them() -> None:
    count = MAX_CONCURRENT_DOWNLOADS + 2
    trace = await _concurrency_trace(count)
    expected = (MAX_CONCURRENT_DOWNLOADS, MAX_CONCURRENT_DOWNLOADS, [b"abc"] * count)
    assert trace == expected, "the downloads were not limited or a download was lost"


def test_limits_downloads_again_in_a_second_event_loop() -> None:
    count = MAX_CONCURRENT_DOWNLOADS + 3
    asyncio.run(_concurrency_trace(count))
    trace = asyncio.run(_concurrency_trace(count))
    expected = (MAX_CONCURRENT_DOWNLOADS, MAX_CONCURRENT_DOWNLOADS, [b"abc"] * count)
    assert trace == expected, "a second event loop could not wait for a free slot"
