import asyncio
from collections.abc import Callable

from bot.services.media.animation.limits import MAX_CONCURRENT_ANIMATIONS

_animation_semaphore = asyncio.Semaphore(MAX_CONCURRENT_ANIMATIONS)


async def extract_with_limit(
    data: bytes,
    media_type: str,
    extractor: Callable[[bytes, str], list[bytes]],
    semaphore: asyncio.Semaphore | None = None,
) -> list[bytes]:
    """Ограничивает число одновременно выполняемых обработок анимаций."""

    active_semaphore = semaphore or _animation_semaphore

    async with active_semaphore:
        task = asyncio.create_task(asyncio.to_thread(extractor, data, media_type))

        try:
            return await asyncio.shield(task)

        except asyncio.CancelledError:
            # Отмена await не останавливает уже запущенный поток.
            # Дожидаемся его завершения, чтобы не освободить семафор
            # раньше фактического завершения обработки.
            try:
                await task
            finally:
                raise
