"""Обратная совместимость для прежнего пути chat_error_handler."""

from bot.services.chat.errors.handler import handle_chat_error, logger
from bot.services.chat.reporting import report_error

__all__ = ["handle_chat_error"]
