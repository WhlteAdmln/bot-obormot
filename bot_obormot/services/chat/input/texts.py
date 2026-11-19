# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""User-facing text templates for chat input preparation."""

AUDIO_HISTORY_TEMPLATE = "[Голосовое сообщение]: {transcribed_text}"
ANIMATION_HISTORY_TEMPLATE = "[Пользователь отправил анимацию: {media_type}]"
PHOTO_HISTORY_TEXT = "[Пользователь отправил фотографию]"
STICKER_HISTORY_TEXT = "[Пользователь отправил стикер]"
IMAGE_HISTORY_TEXT = "[Пользователь отправил изображение]"
DOCUMENT_HISTORY_TEMPLATE = (
    "[Пользователь отправил документ: {filename} ({document_format})]"
)
RECOGNIZED_SPEECH_TEMPLATE = "{caption}\n\n[Распознанная речь]: {transcribed_text}"
DOCUMENT_CONTENT_TEMPLATE = "[Содержимое документа: {filename}]\n\n{document_text}"
