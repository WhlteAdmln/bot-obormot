# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Модели данных для подготовки входящего сообщения."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import Document


@dataclass
class MessageInfo:
    """Kinds of content found in an incoming Telegram message."""

    file_id: str | None
    media_type: str | None
    audio_file_id: str | None
    audio_filename: str | None
    document: Document | None
    has_media: bool
    has_audio: bool
    has_document: bool
    has_text: bool

    @property
    def has_content(self) -> bool:
        """Returns True when the message carries anything the bot can process."""
        return self.has_media or self.has_audio or self.has_document or self.has_text


@dataclass
class PreparedMessage:
    """Message content prepared for the LLM and for the saved history."""

    user_content: str
    saved_user_text: str
    image_bytes: list[bytes] | None = None
