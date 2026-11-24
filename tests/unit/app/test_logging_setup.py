# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for app logging setup."""

import logging

import pytest

from bot_obormot.app.logging_setup import configure_logging
from bot_obormot.settings import load_settings


def test_configure_logging_redacts_audiodoc_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup redacts the configured audiodoc API keys from log output."""
    settings = load_settings(
        {
            "SUPERVISOR_ID": "1",
            "AUDIODOC_URL": "https://audio.test",
            "AUDIODOC_AUDIO_KEY": "whisper-secret-key",
            "AUDIODOC_DOCUMENT_KEY": "document-secret-key",
        }
    )

    with caplog.at_level(logging.WARNING):
        configure_logging(settings)
        logging.getLogger("bot_obormot.main").warning(
            "Configured keys: %s %s",
            settings.AUDIODOC_AUDIO_KEY,
            settings.AUDIODOC_DOCUMENT_KEY,
        )

    expected_fragment = "whisper-secret-key"
    assert expected_fragment not in caplog.text
    expected_fragment = "document-secret-key"
    assert expected_fragment not in caplog.text
