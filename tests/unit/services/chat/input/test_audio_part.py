# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for input audio part."""

from __future__ import annotations

import logging

import pytest

from bot_obormot.services.chat.input import audio_part as audio_module
from tests.support.message_input import make_info, make_message
from tests.support.settings import make_settings


async def _prepare(transcript: str, events: list[object] | None = None) -> str:
    recorded = events if events is not None else []
    info = make_info(
        audio_file_id="voice-id", audio_filename="voice.ogg", has_audio=True
    )

    def validate(_message: object) -> None:
        recorded.append("validate")

    async def download(_message: object, file_id: str) -> bytes:
        recorded.append(("download", file_id))
        return b"audio-bytes"

    async def transcribe(data: object, filename: object) -> str:
        recorded.append(("transcribe", data, filename))
        return transcript

    return await audio_module.prepare_audio(
        make_message(),
        info,
        duration_validator=validate,
        downloader=download,
        transcriber=transcribe,
        settings=make_settings(),
    )


@pytest.mark.asyncio
async def test_prepare_audio_returns_the_transcript() -> None:
    transcript = "Распознано"
    result = await _prepare(transcript)
    assert result == transcript, "the transcript was not returned"


@pytest.mark.asyncio
async def test_prepare_audio_does_not_log_the_transcript(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transcript = "Секретная фраза пользователя"
    with caplog.at_level(logging.INFO, logger=audio_module.logger.name):
        await _prepare(transcript)
    assert transcript not in caplog.text, "the transcript leaked into the log"


@pytest.mark.asyncio
async def test_prepare_audio_logs_the_transcript_length(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transcript = "Привет, бот"
    length_log = "AUDIO: recognized 11 characters"
    with caplog.at_level(logging.INFO, logger=audio_module.logger.name):
        await _prepare(transcript)
    assert length_log in caplog.text, "the transcript length was not logged"


@pytest.mark.asyncio
async def test_prepare_audio_does_not_log_the_recognized_text_marker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    transcript = "Перезвони завтра"
    marker = "Recognized audio text"
    with caplog.at_level(logging.INFO, logger=audio_module.logger.name):
        await _prepare(transcript)
    assert marker not in caplog.text, "the recognized text marker was logged"


@pytest.mark.asyncio
async def test_prepare_audio_validates_downloads_and_transcribes_in_order() -> None:
    events: list[object] = []
    await _prepare("Ок", events)
    expected = [
        "validate",
        ("download", "voice-id"),
        ("transcribe", b"audio-bytes", "voice.ogg"),
    ]
    assert events == expected, "the audio steps ran in another order"
