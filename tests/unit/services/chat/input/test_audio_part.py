# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input audio part."""

from __future__ import annotations

import logging

import pytest

from bot_obormot.services.chat.input import audio_part as audio_module
from tests.support.message_input import make_info, make_message
from tests.support.settings import make_settings


@pytest.mark.asyncio
async def test_prepare_audio_preserves_validation_download_and_transcription_order(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prepare audio preserves validation download and transcription order."""
    events = []
    info = make_info(
        audio_file_id="voice-id", audio_filename="voice.ogg", has_audio=True
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

    expected_result = "Распознано"
    assert result == expected_result
    expected_fragment = "Распознано"
    assert expected_fragment not in caplog.text
    expected_fragment = "AUDIO: recognized 10 characters"
    assert expected_fragment in caplog.text
    expected_fragment = "Recognized audio text"
    assert expected_fragment not in caplog.text
    assert events == [
        "validate",
        ("download", "voice-id"),
        ("transcribe", b"audio-bytes", "voice.ogg"),
    ]
