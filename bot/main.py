"""Тонкая точка входа; реализация находится в :mod:`bot.app`."""

import asyncio

from bot.app.background.image_cleanup import (
    IMAGE_CLEANUP_INTERVAL,
    periodic_image_cleanup,
)
from bot.app.bootstrap import main

__all__ = ["IMAGE_CLEANUP_INTERVAL", "main", "periodic_image_cleanup"]


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
