# Copyright (c) 2026 Nikolai Zelensky
# SPDX-License-Identifier: MIT

"""Cleanup of old and orphaned images."""

import asyncio
import logging
import time
from collections.abc import Callable
from pathlib import Path

import aiosqlite

from bot_obormot.services.database.files.image_storage import (
    delete_image,
    list_image_files,
)
from bot_obormot.services.database.files.image_storage import (
    is_managed_image as is_managed_image_path,
)
from bot_obormot.services.database.repositories import media as media_repository


def _validate_cleanup_options(retention_days: int, orphan_grace_hours: int) -> None:
    if retention_days < 1:
        msg = "retention_days must be at least 1."
        raise ValueError(msg)
    if orphan_grace_hours < 1:
        msg = "orphan_grace_hours must be at least 1."
        raise ValueError(msg)


async def _load_cleanup_targets(
    connection: aiosqlite.Connection,
    images_dir: Path,
    retention_days: int,
) -> tuple[list[Path], set[Path], Path]:
    old_rows = await media_repository.fetch_old_media_rows(
        connection,
        retention_days,
    )
    old_paths = [Path(row["file_path"]) for row in old_rows if row["file_path"]]

    # Delete only media records; message rows remain in history.
    await media_repository.delete_old_media_records(connection, retention_days)

    referenced_file_paths = await media_repository.fetch_referenced_media_paths(
        connection
    )
    referenced_paths = set()
    for file_path in referenced_file_paths:
        resolved_path = await asyncio.to_thread(Path(file_path).resolve)
        referenced_paths.add(resolved_path)

    resolved_images_dir = await asyncio.to_thread(images_dir.resolve)
    return old_paths, referenced_paths, resolved_images_dir


async def _delete_old_images(
    old_paths: list[Path],
    resolved_images_dir: Path,
    delete_image_file: Callable[[Path], None],
    logger: logging.Logger,
) -> tuple[int, int]:
    deleted_old = 0
    failed = 0

    for image_path in old_paths:
        if not is_managed_image_path(image_path, resolved_images_dir):
            logger.warning(
                "Skipping image outside images directory: %s",
                image_path,
            )
            continue
        try:
            await asyncio.to_thread(delete_image_file, image_path)
        except OSError:
            failed += 1
            logger.exception("Could not delete old image: %s", image_path)
        else:
            deleted_old += 1

    return deleted_old, failed


async def _delete_orphan_if_stale(
    image_path: Path,
    orphan_cutoff: float,
    delete_image_file: Callable[[Path], None],
) -> bool:
    """Delete an unreferenced image older than the cutoff; report whether it did."""
    stat = await asyncio.to_thread(image_path.stat)
    if stat.st_mtime >= orphan_cutoff:
        return False
    await asyncio.to_thread(delete_image_file, image_path)
    return True


async def _delete_orphan_images(
    resolved_images_dir: Path,
    referenced_paths: set[Path],
    orphan_grace_hours: int,
    delete_image_file: Callable[[Path], None],
    logger: logging.Logger,
) -> tuple[int, int]:
    orphan_cutoff = time.time() - orphan_grace_hours * 60 * 60
    failed = 0
    try:
        image_files = await asyncio.to_thread(list_image_files, resolved_images_dir)
    except OSError:
        logger.exception(
            "Could not scan images directory: %s",
            resolved_images_dir,
        )
        image_files = []
        failed += 1

    deleted_orphans = 0
    for image_path in image_files:
        if not image_path.is_file() or not is_managed_image_path(
            image_path,
            resolved_images_dir,
        ):
            continue
        resolved_path = image_path.resolve()
        if resolved_path in referenced_paths:
            continue
        try:
            deleted = await _delete_orphan_if_stale(
                image_path, orphan_cutoff, delete_image_file
            )
        except OSError:
            failed += 1
            logger.exception("Could not delete orphan image: %s", image_path)
        else:
            if deleted:
                deleted_orphans += 1

    return deleted_orphans, failed


async def cleanup_old_images(
    connection: aiosqlite.Connection,
    images_dir: Path,
    retention_days: int,
    orphan_grace_hours: int,
    logger: logging.Logger,
    delete_image_file: Callable[[Path], None] = delete_image,
) -> dict[str, int]:
    """Delete old images and files without database references.

    Text messages are preserved, and files outside images_dir are left untouched.
    """
    _validate_cleanup_options(retention_days, orphan_grace_hours)
    old_paths, referenced_paths, resolved_images_dir = await _load_cleanup_targets(
        connection,
        images_dir,
        retention_days,
    )
    deleted_old, failed = await _delete_old_images(
        old_paths,
        resolved_images_dir,
        delete_image_file,
        logger,
    )
    deleted_orphans, orphan_failures = await _delete_orphan_images(
        resolved_images_dir,
        referenced_paths,
        orphan_grace_hours,
        delete_image_file,
        logger,
    )
    failed += orphan_failures

    result = {
        "old_images": deleted_old,
        "orphan_images": deleted_orphans,
        "failed": failed,
    }
    logger.info(
        "Image cleanup completed: old=%s, orphans=%s, failed=%s",
        deleted_old,
        deleted_orphans,
        failed,
    )
    return result
