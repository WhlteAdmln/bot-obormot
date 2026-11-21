# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while transcribing audio through audiodoc."""

from typing import ClassVar

from bot_obormot.errors.base import AppError


class AudiodocError(AppError):
    """Audio recognition failed in the audiodoc service."""

    code: ClassVar[str] = "audiodoc_error"
    public_message: ClassVar[str] = "Audio transcription failed"


class AudiodocEmptyAudioError(AudiodocError):
    """No speech could be recognized in the audio."""

    code: ClassVar[str] = "audiodoc_empty_audio"
    public_message: ClassVar[str] = "No speech detected in audio"


class AudiodocUnavailableError(AudiodocError):
    """The audio transcription service is unavailable."""

    code: ClassVar[str] = "audiodoc_unavailable"
    public_message: ClassVar[str] = "Audio transcription service is unavailable"


class AudiodocTimeoutError(AudiodocError):
    """Timed out while waiting for the audio transcription service."""

    code: ClassVar[str] = "audiodoc_timeout"
    public_message: ClassVar[str] = "Audio transcription timed out"


class AudiodocAPIError(AudiodocError):
    """The audio transcription service returned an API error."""

    code: ClassVar[str] = "audiodoc_api_error"
    public_message: ClassVar[str] = "Audio transcription service returned an error"
