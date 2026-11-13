# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Формирование текстового представления сообщения для истории."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiogram.types import Message

    from bot.services.chat.input.models import MessageInfo


def build_saved_user_text(
    message: Message,
    info: MessageInfo,
    *,
    text_override: str | None,
    transcribed_text: str | None,
    document_format: str | None,
) -> str | None:
    """Формирует прежнее текстовое описание сообщения для БД."""
    if info.has_audio:
        saved_user_text = f"[Голосовое сообщение]: {transcribed_text}"

        if message.caption:
            saved_user_text = f"{message.caption}\n\n{saved_user_text}"

    elif info.has_media:
        if info.media_type in ("tgs", "webm", "gif", "mp4"):
            saved_user_text = f"[Пользователь отправил анимацию: {info.media_type}]"

        elif message.photo:
            saved_user_text = "[Пользователь отправил фотографию]"

        elif message.sticker:
            saved_user_text = "[Пользователь отправил стикер]"

        else:
            saved_user_text = "[Пользователь отправил изображение]"

        if message.caption:
            saved_user_text += f" {message.caption}"

    elif info.has_document:
        document = info.document

        saved_user_text = (
            f"[Пользователь отправил документ: "
            f"{document.file_name or 'document'} "
            f"({document_format.upper()})]"
        )

        if message.caption:
            saved_user_text += f" {message.caption}"

    else:
        saved_user_text = text_override if text_override is not None else message.text

    return saved_user_text
