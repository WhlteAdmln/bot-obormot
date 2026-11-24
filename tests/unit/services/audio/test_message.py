# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for audio message."""

from types import SimpleNamespace

from bot_obormot.services.audio import (
    get_audio_info,
)
from tests.support.audio_documents import make_message


def test_get_audio_info_preserves_voice_audio_and_video_note_names() -> None:
    assert get_audio_info(make_message(voice=SimpleNamespace(file_id="voice-id"))) == (
        "voice-id",
        "voice.ogg",
    )
    assert get_audio_info(
        make_message(audio=SimpleNamespace(file_id="audio-id", file_name="track.wav"))
    ) == ("audio-id", "track.wav")
    assert get_audio_info(
        make_message(audio=SimpleNamespace(file_id="audio-id", file_name=None))
    ) == ("audio-id", "audio.mp3")
    assert get_audio_info(
        make_message(video_note=SimpleNamespace(file_id="note-id"))
    ) == ("note-id", "video_note.mp4")
    assert get_audio_info(make_message()) == (None, None)
