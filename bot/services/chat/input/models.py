"""Модели данных для подготовки входящего сообщения."""

from dataclasses import dataclass


@dataclass
class MessageInfo:
    file_id: str | None
    media_type: str | None
    audio_file_id: str | None
    audio_filename: str | None
    document: object | None
    has_media: bool
    has_audio: bool
    has_document: bool
    has_text: bool

    @property
    def has_content(self) -> bool:
        return self.has_media or self.has_audio or self.has_document or self.has_text


@dataclass
class PreparedMessage:
    user_content: str
    saved_user_text: str
    image_bytes: list[bytes] | None = None
