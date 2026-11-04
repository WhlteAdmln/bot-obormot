"""Обратная совместимость для прежнего пути chat_logging."""

from bot.services.chat.incoming_log import log_incoming_message, logger

__all__ = ["log_incoming_message"]
