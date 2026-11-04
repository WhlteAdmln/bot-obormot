"""Периодическая фоновая очистка старых и осиротевших изображений."""

import asyncio
import logging

from bot.services.database import db

logger = logging.getLogger("bot.main")
IMAGE_CLEANUP_INTERVAL = 24 * 60 * 60


async def periodic_image_cleanup() -> None:
    """Выполняет очистку изображений раз в сутки."""
    while True:
        try:
            result = await db.cleanup_old_images(
                retention_days=30,
                orphan_grace_hours=24,
            )
            logger.debug("Image cleanup result: %s", result)

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception("Scheduled image cleanup failed")

        await asyncio.sleep(IMAGE_CLEANUP_INTERVAL)
