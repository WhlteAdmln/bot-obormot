"""Чтение HTTP-ответов с ограничением размера."""

import aiohttp

MAX_SERVICE_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 МБ
MAX_ERROR_BODY_BYTES = 2048


async def read_limited_body(
    response: aiohttp.ClientResponse,
    limit: int,
) -> bytes | None:
    """Возвращает тело ответа или None, если оно больше limit байт."""
    if response.content_length is not None and response.content_length > limit:
        return None

    chunks: list[bytes] = []
    total = 0

    async for chunk in response.content.iter_chunked(64 * 1024):
        total += len(chunk)

        if total > limit:
            return None

        chunks.append(chunk)

    return b"".join(chunks)
