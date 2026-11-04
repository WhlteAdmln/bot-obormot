"""Фоновые задачи приложения."""

from bot.app.background.image_cleanup import (
    IMAGE_CLEANUP_INTERVAL,
    periodic_image_cleanup,
)

__all__ = ["IMAGE_CLEANUP_INTERVAL", "periodic_image_cleanup"]
