# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Periodically clean up old and orphaned images."""

import asyncio
import logging

from bot_obormot.services.database import Database

logger = logging.getLogger("bot_obormot.main")
IMAGE_CLEANUP_INTERVAL = 24 * 60 * 60


async def periodic_image_cleanup(database: Database) -> None:
    """Clean up images periodically."""
    while True:
        try:
            result = await database.cleanup_old_images(
                retention_days=30,
                orphan_grace_hours=24,
            )
            logger.debug("Image cleanup result: %s", result)

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception("Scheduled image cleanup failed")

        await asyncio.sleep(IMAGE_CLEANUP_INTERVAL)
