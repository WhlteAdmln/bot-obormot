# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Compatible public API for audio processing."""

from bot.services.audio.client import transcribe_audio
from bot.services.audio.message import get_audio_info
from bot.services.audio.validation import MAX_AUDIO_DURATION, validate_audio_duration

__all__ = [
    "MAX_AUDIO_DURATION",
    "get_audio_info",
    "transcribe_audio",
    "validate_audio_duration",
]
