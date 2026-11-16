# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Exceptions raised while transcribing audio through audiodoc."""

from typing import ClassVar

from bot.errors.base import AppError


class AudiodocError(AppError):
    """Ошибка распознавания аудио сервисом audiodoc."""

    code: ClassVar[str] = "audiodoc_error"
    public_message: ClassVar[str] = "Audio transcription failed"


class AudiodocEmptyAudioError(AudiodocError):
    """В аудио не удалось распознать речь."""

    code: ClassVar[str] = "audiodoc_empty_audio"
    public_message: ClassVar[str] = "No speech detected in audio"


class AudiodocUnavailableError(AudiodocError):
    """Сервис распознавания аудио недоступен."""

    code: ClassVar[str] = "audiodoc_unavailable"
    public_message: ClassVar[str] = "Audio transcription service is unavailable"


class AudiodocTimeoutError(AudiodocError):
    """Истекло время ожидания сервиса распознавания аудио."""

    code: ClassVar[str] = "audiodoc_timeout"
    public_message: ClassVar[str] = "Audio transcription timed out"


class AudiodocAPIError(AudiodocError):
    """Сервис распознавания аудио вернул ошибку API."""

    code: ClassVar[str] = "audiodoc_api_error"
    public_message: ClassVar[str] = "Audio transcription service returned an error"


# Deprecated aliases kept for one release. Use the ``Audiodoc*`` names instead.
WhisperError = AudiodocError
WhisperEmptyAudioError = AudiodocEmptyAudioError
WhisperUnavailableError = AudiodocUnavailableError
WhisperTimeoutError = AudiodocTimeoutError
WhisperAPIError = AudiodocAPIError
