# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for project telegram service modules."""

from bot_obormot.services import telegram
from bot_obormot.services.telegram import keep_typing
from bot_obormot.services.telegram.downloader import TelegramDownloader


def test_telegram_services_are_imported_from_canonical_modules() -> None:
    assert telegram.TelegramDownloader is TelegramDownloader
    expected_module = "bot_obormot.services.telegram.chat_action"
    assert keep_typing.__module__ == expected_module
