# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for errors catalog."""

from bot_obormot.services.chat.errors import catalog


def test_chat_error_catalog_preserves_original_if_elif_priority() -> None:
    expected = [
        "InputTooLongError",
        "TelegramFileTooBigError",
        "DocumentTooLongError",
        "DocumentTimeoutError",
        "DocumentUnavailableError",
        "DocumentAPIError",
        "AudiodocEmptyAudioError",
        "AudiodocTimeoutError",
        "AudiodocUnavailableError",
        "AudiodocAPIError",
        "AudiodocError",
        "MediaError",
        "TelegramError",
        "LLMTimeoutError",
        "LLMUnavailableError",
        "LLMAPIError",
        "LLMEmptyResponseError",
        "DatabaseError",
    ]
    names = [rule.error_type.__name__ for rule in catalog.CHAT_ERROR_RULES]
    assert names == expected, "the error rules are in another order"
