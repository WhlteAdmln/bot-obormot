# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for audio message."""

from types import SimpleNamespace

import pytest

from bot_obormot.services.audio import (
    get_audio_info,
)
from tests.support.audio_documents import make_message


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        (
            make_message(voice=SimpleNamespace(file_id="voice-id")),
            ("voice-id", "voice.ogg"),
        ),
        (
            make_message(
                audio=SimpleNamespace(file_id="audio-id", file_name="track.wav")
            ),
            ("audio-id", "track.wav"),
        ),
        (
            make_message(
                audio=SimpleNamespace(file_id="audio-nameless", file_name=None)
            ),
            ("audio-nameless", "audio.mp3"),
        ),
        (
            make_message(video_note=SimpleNamespace(file_id="note-id")),
            ("note-id", "video_note.mp4"),
        ),
        (make_message(), (None, None)),
    ],
)
def test_get_audio_info_preserves_voice_audio_and_video_note_names(
    message: SimpleNamespace, expected: tuple[str | None, str | None]
) -> None:
    assert get_audio_info(message) == expected, "the audio file name was not kept"
