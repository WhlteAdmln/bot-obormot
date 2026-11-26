# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for project telegram service modules."""

from bot_obormot.services import telegram
from bot_obormot.services.telegram import keep_typing
from bot_obormot.services.telegram.downloader import TelegramDownloader


def test_reexports_the_telegram_downloader_from_the_package() -> None:
    assert telegram.TelegramDownloader is TelegramDownloader, (
        "package exports a different downloader"
    )


def test_loads_keep_typing_from_the_chat_action_module() -> None:
    expected_module = "bot_obormot.services.telegram.chat_action"
    assert keep_typing.__module__ == expected_module, (
        "keep_typing is defined in an unexpected module"
    )
