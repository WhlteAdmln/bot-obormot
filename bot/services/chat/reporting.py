import logging

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


logger = logging.getLogger("bot.services.chat.reporting")


async def safe_edit(message: Message, text: str):
    """Безопасно редактирует сообщение."""

    try:
        await message.edit_text(
            text,
            parse_mode=ParseMode.HTML,
        )
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            raise


async def report_error(
    message: Message,
    status: Message | None,
    text: str,
):
    """Безопасно сообщает пользователю об ошибке."""

    if status is None:
        try:
            await message.answer(text)
        except Exception:
            logger.exception("Could not send error message")
        return

    try:
        await safe_edit(status, text)
    except Exception:
        logger.exception("Could not edit status message")
