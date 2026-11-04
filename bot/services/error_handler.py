"""Обратная совместимость для прежнего пути error_handler."""

from bot.services.chat.reporting import safe_edit, report_error
from bot.services.chat.reporting import logger

__all__ = ["safe_edit", "report_error"]
