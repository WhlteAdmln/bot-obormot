# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Logging of incoming Telegram messages."""

import logging

from aiogram.types import Message

from bot.utils.text import log_safe

logger = logging.getLogger("bot.services.chat.incoming_log")


def log_incoming_message(message: Message) -> None:
    """Записывает информацию о входящем сообщении."""
    logger.info(
        "INCOMING MESSAGE: type=%s, animation=%s, video=%s, "
        "document=%s, sticker=%s, photo=%s",
        message.content_type,
        bool(message.animation),
        bool(message.video),
        bool(message.document),
        bool(message.sticker),
        bool(message.photo),
    )

    if message.document:
        logger.info(
            "DOCUMENT INFO: filename=%s, mime_type=%s",
            log_safe(message.document.file_name),
            log_safe(message.document.mime_type),
        )

    if message.animation:
        logger.info(
            "ANIMATION INFO: mime_type=%s, file_id=%s",
            log_safe(message.animation.mime_type),
            message.animation.file_id,
        )
