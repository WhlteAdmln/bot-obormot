from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import Message


def get_audio_info(message: Message):
    """Определяет тип голосового или аудиосообщения."""

    if message.voice:
        return message.voice.file_id, "voice.ogg"

    if message.audio:
        filename = message.audio.file_name or "audio.mp3"
        return message.audio.file_id, filename

    if message.video_note:
        return message.video_note.file_id, "video_note.mp4"

    return None, None
