from aiogram.types import Message


def get_media_info(message: Message):
    """Определяет тип и file_id входящего медиа."""

    if message.photo:
        return message.photo[-1].file_id, "image"

    if message.animation:
        return message.animation.file_id, "mp4"

    if message.video:
        return message.video.file_id, "mp4"

    if message.sticker:
        sticker = message.sticker

        if sticker.is_animated:
            return sticker.file_id, "tgs"

        if sticker.is_video:
            return sticker.file_id, "webm"

        return sticker.file_id, "image"

    if message.document:
        document = message.document
        filename = (document.file_name or "").lower()
        mime_type = (document.mime_type or "").lower()

        if filename.endswith(".gif") or mime_type == "image/gif":
            return document.file_id, "gif"

        if filename.endswith(".webm") or mime_type == "video/webm":
            return document.file_id, "webm"

        if filename.endswith(".mp4") or mime_type == "video/mp4":
            return document.file_id, "mp4"

    return None, None
