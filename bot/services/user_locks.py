"""Обратная совместимость для прежнего пути user_locks."""

from bot.services.chat.locks import get_user_lock, _user_locks

__all__ = ["get_user_lock"]
