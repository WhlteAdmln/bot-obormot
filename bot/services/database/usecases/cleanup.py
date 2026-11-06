"""Сценарий очистки старых и осиротевших изображений."""

import asyncio
import logging
import time
from pathlib import Path

import aiosqlite

from bot.services.database.files.image_storage import (
    delete_image,
    list_image_files,
)
from bot.services.database.files.image_storage import (
    is_managed_image as is_managed_image_path,
)
from bot.services.database.repositories import media as media_repository


async def cleanup_old_images(
    connection: aiosqlite.Connection,
    images_dir: Path,
    retention_days: int,
    orphan_grace_hours: int,
    logger: logging.Logger,
    delete_image_file=delete_image,
) -> dict[str, int]:
    """Удаляет старые изображения и файлы без ссылок в БД.

    Текстовые сообщения сохраняются, а файлы вне images_dir не затрагиваются.
    """
    if retention_days < 1:
        raise ValueError("retention_days должен быть не меньше 1.")
    if orphan_grace_hours < 1:
        raise ValueError("orphan_grace_hours должен быть не меньше 1.")

    old_rows = await media_repository.fetch_old_media_rows(
        connection,
        retention_days,
    )
    old_paths = [Path(row["file_path"]) for row in old_rows if row["file_path"]]

    # Удаляем только записи о медиа; строки сообщений остаются в истории.
    await media_repository.delete_old_media_records(connection, retention_days)

    referenced_file_paths = await media_repository.fetch_referenced_media_paths(
        connection
    )
    referenced_paths = set()

    for file_path in referenced_file_paths:
        resolved_path = await asyncio.to_thread(Path(file_path).resolve)
        referenced_paths.add(resolved_path)

    resolved_images_dir = await asyncio.to_thread(images_dir.resolve)

    def is_managed_image(path: Path) -> bool:
        """Проверяет, что файл создан нашим хранилищем изображений."""
        return is_managed_image_path(path, resolved_images_dir)

    deleted_old = 0
    deleted_orphans = 0
    failed = 0

    for image_path in old_paths:
        if not is_managed_image(image_path):
            logger.warning(
                "Skipping image outside images directory: %s",
                image_path,
            )
            continue
        try:
            await asyncio.to_thread(delete_image_file, image_path)
            deleted_old += 1
        except OSError:
            failed += 1
            logger.exception("Could not delete old image: %s", image_path)

    orphan_cutoff = time.time() - orphan_grace_hours * 60 * 60
    try:
        image_files = await asyncio.to_thread(list_image_files, resolved_images_dir)
    except OSError:
        logger.exception(
            "Could not scan images directory: %s",
            resolved_images_dir,
        )
        image_files = []
        failed += 1

    for image_path in image_files:
        if not image_path.is_file() or not is_managed_image(image_path):
            continue
        resolved_path = image_path.resolve()
        if resolved_path in referenced_paths:
            continue
        try:
            stat = await asyncio.to_thread(image_path.stat)
            if stat.st_mtime >= orphan_cutoff:
                continue
            await asyncio.to_thread(delete_image_file, image_path)
            deleted_orphans += 1
        except OSError:
            failed += 1
            logger.exception("Could not delete orphan image: %s", image_path)

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
