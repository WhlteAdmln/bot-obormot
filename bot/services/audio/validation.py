# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Validation of incoming audio messages."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bot.errors import MediaError

if TYPE_CHECKING:
    from aiogram.types import Message


MAX_AUDIO_DURATION = 300


def validate_audio_duration(message: Message) -> None:
    """Проверяет длительность входящего аудио."""
    duration = None

    if message.voice:
        duration = message.voice.duration
    elif message.audio:
        duration = message.audio.duration
    elif message.video_note:
        duration = message.video_note.duration

    if duration is not None and duration > MAX_AUDIO_DURATION:
        msg = "Аудиофайл слишком длинный (максимум 5 минут)."
        raise MediaError(msg)
