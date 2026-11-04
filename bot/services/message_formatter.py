"""Обратная совместимость для прежнего пути message_formatter."""

from bot.services.chat.formatting.roleplay import format_roleplay, _render_segment
from bot.services.chat.formatting.splitter import split_formatted_message, _utf16_length

__all__ = ["format_roleplay", "split_formatted_message"]
