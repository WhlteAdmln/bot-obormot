import logging

from aiogram.types import Message


logger = logging.getLogger("bot.services.chat_logging")


def log_incoming_message(message: Message):
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
            message.document.file_name,
            message.document.mime_type,
        )

    if message.animation:
        logger.info(
            "ANIMATION INFO: mime_type=%s, file_id=%s",
            message.animation.mime_type,
            message.animation.file_id,
        )
