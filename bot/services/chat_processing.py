"""Обратная совместимость для прежнего пути chat_processing."""

from bot.services.chat.pipeline import process_chat, logger

__all__ = ["process_chat"]
