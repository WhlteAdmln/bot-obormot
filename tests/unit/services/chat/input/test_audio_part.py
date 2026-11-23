# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input audio part."""

from __future__ import annotations

import logging

import pytest

from bot_obormot.services.chat.input import (
    MessageInfo,
)
from bot_obormot.services.chat.input import audio_part as audio_module
from tests.support.message_input import make_message
from tests.support.settings import make_settings


@pytest.mark.asyncio
async def test_prepare_audio_preserves_validation_download_and_transcription_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prepare audio preserves validation download and transcription order."""
    events = []
    info = MessageInfo(
        file_id=None,
        media_type=None,
        audio_file_id="voice-id",
        audio_filename="voice.ogg",
        document=None,
        has_media=False,
        has_audio=True,
        has_document=False,
        has_text=False,
    )

    def validate(_message: object) -> None:
        events.append("validate")

    async def download(_message: object, file_id: str) -> bytes:
        events.append(("download", file_id))
        return b"audio-bytes"

    async def transcribe(data: object, filename: object) -> str:
        events.append(("transcribe", data, filename))
        return "Распознано"

    with caplog.at_level(logging.INFO, logger=audio_module.logger.name):
        result = await audio_module.prepare_audio(
            make_message(),
            info,
            duration_validator=validate,
            downloader=download,
            transcriber=transcribe,
            settings=make_settings(),
        )

    assert result == "Распознано"
    assert "Распознано" not in caplog.text
    assert "AUDIO: recognized 10 characters" in caplog.text
    assert "Recognized audio text" not in caplog.text
    assert events == [
        "validate",
        ("download", "voice-id"),
        ("transcribe", b"audio-bytes", "voice.ogg"),
    ]
