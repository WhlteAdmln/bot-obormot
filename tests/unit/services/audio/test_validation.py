# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for audio validation."""

from types import SimpleNamespace

import pytest

from bot_obormot.errors import (
    MediaError,
)
from bot_obormot.services.audio import (
    MAX_AUDIO_DURATION,
    validate_audio_duration,
)
from tests.support.audio_documents import make_message


def test_validate_audio_duration_keeps_five_minute_boundary() -> None:
    """Validate audio duration keeps five minute boundary."""
    expected_max_audio_duration = 300
    assert expected_max_audio_duration == MAX_AUDIO_DURATION
    validate_audio_duration(make_message(voice=SimpleNamespace(duration=300)))
    with pytest.raises(MediaError, match="Аудиофайл слишком длинный"):
        validate_audio_duration(make_message(voice=SimpleNamespace(duration=301)))


def test_validate_audio_duration_checks_audio_and_video_note() -> None:
    """Validate audio duration checks audio and video note."""
    with pytest.raises(MediaError):
        validate_audio_duration(make_message(audio=SimpleNamespace(duration=301)))
    with pytest.raises(MediaError):
        validate_audio_duration(make_message(video_note=SimpleNamespace(duration=301)))
