"""Логирование ошибок чата и отправка ответа пользователю."""

import logging

from aiogram.types import Message

from bot.services.chat.errors.catalog import CHAT_ERROR_RULES, ChatErrorRule
from bot.services.chat.errors import texts
from bot.services.chat.reporting import report_error
from bot.utils.text import log_safe


logger = logging.getLogger("bot.services.chat.errors.handler")


def _log_rule_error(rule: ChatErrorRule, error: Exception, user_id: int) -> None:
    if rule.log_method is None or rule.log_template is None:
        return

    values = {
        "user_id": user_id,
        "error": log_safe(error, 300),
        "status": getattr(error, "status", None),
        "detail": log_safe(getattr(error, "detail", None), 300),
    }
    args = tuple(values[field] for field in rule.log_fields)
    kwargs = {}
    if rule.traceback:
        kwargs["exc_info"] = (type(error), error, error.__traceback__)

    getattr(logger, rule.log_method)(rule.log_template, *args, **kwargs)


async def handle_chat_error(
    message: Message, status, user_id: int, error: Exception
) -> None:
    """Логирует ошибку обработки сообщения и уведомляет пользователя."""
    for rule in CHAT_ERROR_RULES:
        if isinstance(error, rule.error_type):
            _log_rule_error(rule, error, user_id)
            user_message = (
                rule.user_message(error)
                if callable(rule.user_message)
                else rule.user_message
            )
            await report_error(message, status, user_message)
            return

    logger.error(
        "Unexpected error in handle_message for user_id=%s",
        user_id,
        exc_info=(type(error), error, error.__traceback__),
    )
    await report_error(
        message,
        status,
        texts.UNEXPECTED_ERROR,
    )
