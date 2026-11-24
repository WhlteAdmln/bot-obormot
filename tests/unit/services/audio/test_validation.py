# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Tests for audio validation."""

from types import SimpleNamespace

import pytest

from bot_obormot.errors import MediaError
from bot_obormot.services.audio import validate_audio_duration
from tests.support.audio_documents import make_message


def _rejection(**media: object) -> str:
    try:
        validate_audio_duration(make_message(**media))
    except MediaError as error:
        return str(error)
    return ""


@pytest.mark.parametrize(
    "media",
    [
        {"voice": SimpleNamespace(duration=301)},
        {"audio": SimpleNamespace(duration=301)},
        {"video_note": SimpleNamespace(duration=301)},
        {"audio": SimpleNamespace(duration=86_400)},
        {"voice": SimpleNamespace(duration=2**63)},
    ],
    ids=["voice", "audio", "video-note", "one-day", "huge"],
)
def test_rejects_media_longer_than_five_minutes(media: dict[str, object]) -> None:
    expected = "Аудиофайл слишком длинный (максимум 5 минут)."
    assert _rejection(**media) == expected, "long media must be rejected"


@pytest.mark.parametrize(
    "media",
    [
        {"voice": SimpleNamespace(duration=300)},
        {"audio": SimpleNamespace(duration=300)},
        {"video_note": SimpleNamespace(duration=0)},
        {"voice": SimpleNamespace(duration=None)},
        {"voice": SimpleNamespace(duration=-5)},
        {},
    ],
    ids=["voice-at-limit", "audio-at-limit", "zero", "unknown", "negative", "none"],
)
def test_accepts_media_up_to_five_minutes(media: dict[str, object]) -> None:
    expected = ""
    assert _rejection(**media) == expected, "short media must be accepted"
